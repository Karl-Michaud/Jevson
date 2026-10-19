"""`Jevson`: the public entry point. Compiles the schema, runs the executor, and checks the result.

`Jevson(backend, llm=None, extractors=None, config=None, cost_sink=None)` with
`resolve()` / `aresolve(schema, source, *, known=None, redraft_budget=None)` (DESIGN §8). There is no
default backend: constructing a `DecisionsBackend` is an explicit choice to spend money.

- `CompileError`, `PreflightError` and `UsageError` are raised before anything is spent; `known=`
  values are checked against their field's declared values before the first call, then recorded as
  `decided_by: caller`.
- For a Pydantic model, `.value` must also pass `model_validate`, else `satisfies_schema` is False
  and each error is a `Violation` with keyword `model_validate` [L18].
- With `raise_on_unresolved_required`, an unresolved required field raises `SchemaViolation`
  carrying the `Result`.
- `resolve()` submits `aresolve()` to the library-owned loop (`execute/loop.py`) and blocks; inside
  a running loop it raises `UsageError` pointing at `aresolve()`.
- Lifecycle: `async with Jevson(...)` enters its backend's `async with`, if it has one, so calls on
  that loop share one client. `close()` and `aclose()` refuse further calls and close the backend
  too (its `close()` / `aclose()`, if it has them), so a backend should not be shared between
  `Jevson` instances that are closed separately.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from types import TracebackType
from typing import Any, cast

from jevson.compile.compiler import compile_schema
from jevson.compile.normalise import Kind, SchemaNode, normalise_schema
from jevson.config import JevsonConfig
from jevson.errors import PreflightError, SchemaViolation, UsageError
from jevson.execute import loop
from jevson.execute.executor import execute
from jevson.graph import DecisionGraph
from jevson.protocols import LLM, Backend, CostSink, Extractor
from jevson.result import Result
from jevson.types import DecisionKind, DecisionNode, JSONValue, StepNode, Violation


class Jevson:
    def __init__(
        self,
        backend: Backend,
        llm: LLM | None = None,
        extractors: Mapping[str, Extractor] | None = None,
        config: JevsonConfig | None = None,
        cost_sink: CostSink | None = None,
    ) -> None:
        if not isinstance(backend, Backend):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise UsageError("Jevson needs a backend; there is no default (construct DecisionsBackend explicitly)")
        self._backend = backend
        self._llm = llm
        self._extractors = dict(extractors or {})  # v0: accepted and unused (DESIGN §8)
        self._config = config or JevsonConfig()
        self._cost_sink = cost_sink
        self._closed = False
        self._entered: list[Any] = []

    def __repr__(self) -> str:
        return f"Jevson(backend={self._backend!r}, closed={self._closed})"

    # --- lifecycle ------------------------------------------------------------------------

    def __enter__(self) -> Jevson:
        self._check_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aenter__(self) -> Jevson:
        self._check_open()
        enter = getattr(self._backend, "__aenter__", None)
        if enter is not None:
            await enter()
            self._entered.append(self._backend)
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._entered:
            await self._entered.pop().__aexit__(exc_type, exc, tb)
        await self.aclose()

    def close(self) -> None:
        self._closed = True
        close = getattr(self._backend, "close", None)
        if callable(close):
            close()

    async def aclose(self) -> None:
        self._closed = True
        aclose = getattr(self._backend, "aclose", None)
        if callable(aclose):
            await cast("Callable[[], Awaitable[object]]", aclose)()

    def _check_open(self) -> None:
        if self._closed:
            raise UsageError("this Jevson is closed")

    # --- resolve --------------------------------------------------------------------------

    def resolve(
        self,
        schema: object,
        source: str,
        *,
        known: Mapping[str, JSONValue] | None = None,
        redraft_budget: int | None = None,
    ) -> Result:
        """The synchronous `aresolve()`, run on the library loop; refuses inside a running loop."""
        self._check_open()
        return loop.run(lambda: self.aresolve(schema, source, known=known, redraft_budget=redraft_budget))

    async def aresolve(
        self,
        schema: object,
        source: str,
        *,
        known: Mapping[str, JSONValue] | None = None,
        redraft_budget: int | None = None,
    ) -> Result:
        self._check_open()
        if not isinstance(source, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise PreflightError("aresolve takes exactly one source, as a str")
        config = self._config if redraft_budget is None else replace(self._config, redraft_budget=redraft_budget)
        graph = compile_schema(
            schema, frozenset(self._extractors), config.default_extractor, union_fanout=config.union_fanout
        )
        fields = _fields(normalise_schema(schema))
        checked = _check_known(graph, fields, known)
        result = await execute(
            graph, _json_schema(schema), source,
            backend=self._backend, config=config, known=checked, cost_sink=self._cost_sink, llm=self._llm,
        )  # fmt: skip
        result = _model_validate(schema, result)
        missing = [u.pointer for u in result.unresolved if fields.get(u.pointer, _OPTIONAL).required]
        if config.raise_on_unresolved_required and missing:
            raise SchemaViolation(f"required fields unresolved: {', '.join(missing)}", result)
        return result


_OPTIONAL = SchemaNode("", Kind.REFUSED, required=False)


def _fields(node: SchemaNode) -> dict[str, SchemaNode]:
    """Every property in the normalised tree by pointer; `required` means required at every level."""
    found: dict[str, SchemaNode] = {}
    for _, child in node.properties:
        found[child.pointer] = replace(child, required=child.required and node.required)
        found |= _fields(found[child.pointer])
    for branch in node.branches:  # a union's branches sit at its pointer; only one is selected
        found |= _fields(replace(branch, required=node.required))
    return found


def _check_known(
    graph: DecisionGraph, fields: Mapping[str, SchemaNode], known: Mapping[str, JSONValue] | None
) -> dict[str, JSONValue]:
    if known is None:
        return {}
    if not isinstance(known, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise PreflightError("known= must map JSON pointers to values")
    by_target: dict[str, DecisionNode | StepNode] = {}
    for node in graph.nodes.values():
        if isinstance(node, StepNode) or node.target not in by_target:
            by_target[node.target] = node  # a generative field is known by its step
    constants = {c.pointer for c in graph.constants}  # checked by the executor (`execute/branches.py`)
    for pointer, value in known.items():
        node = by_target.get(pointer)
        if node is None and pointer in constants:
            continue
        if node is None:
            raise PreflightError(f"known= names {pointer!r}, which is not a decided field")
        if not _allowed(node, fields.get(pointer, _OPTIONAL), value):
            raise PreflightError(f"known= value for {pointer!r} is not one of the field's declared values")
    return dict(known)


def _allowed(node: DecisionNode | StepNode, field: SchemaNode, value: JSONValue) -> bool:
    if value is None:
        return field.nullable
    if isinstance(node, StepNode):
        return isinstance(value, str)
    if node.member is not None:  # a multi-label enum array: distinct declared values
        declared = field.items.values if field.items is not None else ()
        items = cast("list[JSONValue]", value) if isinstance(value, list) else None
        return (
            items is not None
            and len(set(map(repr, items))) == len(items)
            and all(any(type(item) is type(v) and item == v for v in declared) for item in items)
        )
    if node.kind is DecisionKind.PREDICATE:
        return isinstance(value, bool)
    return any(type(value) is type(v) and value == v for v in node.values)


def _json_schema(schema: object) -> Mapping[str, Any]:
    method = getattr(schema, "model_json_schema", None)
    return cast("Mapping[str, Any]", method(mode="validation") if method is not None else schema)


def _model_validate(schema: object, result: Result) -> Result:
    validate = getattr(schema, "model_validate", None)
    if validate is None:
        return result
    try:
        validate(result.value)
    except ValueError as error:  # pydantic.ValidationError subclasses ValueError
        errors = cast("list[dict[str, Any]]", getattr(error, "errors", list)())
        extra = [Violation(_pointer(e.get("loc", ())), "model_validate", str(e.get("msg", ""))) for e in errors]
        if not extra:
            extra = [Violation("", "model_validate", type(error).__name__)]
        return replace(result, satisfies_schema=False, violations=(*result.violations, *extra))
    return result


def _pointer(loc: object) -> str:
    parts = cast("tuple[object, ...]", loc) if isinstance(loc, tuple) else ()
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)
