"""`compile_schema()`: a schema → a `DecisionGraph`, or one `CompileError` naming every problem (R14).

Standalone and network-free: normalising, mapping, and graph construction never call a backend,
an extractor, or an LLM, so every refusal happens before anything is spent.
"""

from __future__ import annotations

from collections.abc import Sequence, Set

from jevson.compile.mapping import map_tree
from jevson.compile.normalise import normalise
from jevson.compile.refusal import Refusals
from jevson.errors import RefusalCode
from jevson.graph import DecisionGraph
from jevson.types import DecisionNode


def compile_schema(
    schema: object, extractors: Set[str] = frozenset(), default_extractor: str | None = None
) -> DecisionGraph:
    """Compile a JSON Schema 2020-12 dict or a Pydantic model class into its decision graph.

    `extractors` and `default_extractor` are the extractor *names* of DESIGN §3.5. They are kept so
    reviving source selection (class D) is not a signature change; in v0 `extractors` changes
    nothing, because every `x-jevson.source` refuses whatever it names, and `default_extractor` only
    turns an unbounded field's `unbounded_field` refusal into `source_selection_dropped`.
    """
    del extractors  # v0: no field is source-selected, so no extractor name is ever looked up
    refusals = Refusals()
    nodes = map_tree(normalise(schema, refusals), refusals, default_extractor=default_extractor)
    refuse_duplicate_questions([n for n in nodes if isinstance(n, DecisionNode)], refusals)
    refusals.raise_if_any()
    return DecisionGraph(nodes)


def refuse_duplicate_questions(nodes: Sequence[DecisionNode], refusals: Refusals) -> None:
    """Refuse every decision that renders the same question over the same options as an earlier one.

    Every question in a level shares one input (DESIGN §2), so two such questions get the same answer
    whatever their targets: a silent wrong value. Qualified labels prevent this unless the schema
    declares the collision itself, for example one `x-jevson.question` on two fields."""
    first: dict[tuple[str, tuple[str, ...]], DecisionNode] = {}
    for node in nodes:
        key = (node.question, tuple(option.description for option in node.options))
        earlier = first.setdefault(key, node)
        if earlier is not node:
            refusals.add(
                node.target,
                RefusalCode.DUPLICATE_QUESTION,
                f"asks {node.question!r} over the same options as {earlier.target}, so both would get one "
                "answer; give one of them a distinct x-jevson.question",
            )
