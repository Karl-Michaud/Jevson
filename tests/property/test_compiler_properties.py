"""PLAN §4.3: over generated schemas, `compile_schema()` returns a graph or raises `CompileError`.

Never a third outcome and never a partial graph: a returned graph means nothing anywhere in the
schema was refused, and its nodes are exactly the decidable leaves. Two generators: the normaliser's
adversarial one, and one over the supported subset where the expected nodes are known. A third
mixes refusing leaves into that subset and checks the `CompileError` names exactly them.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jevson import CompileError, compile_schema
from jevson.compile.normalise import normalise
from jevson.compile.refusal import Refusals
from jevson.graph import DecisionGraph
from tests.property.test_normalise_properties import DETERMINISTIC, roots


@DETERMINISTIC
@given(roots, st.sampled_from([None, "llm"]))
def test_compile_schema_returns_a_whole_graph_or_raises_compile_error(schema: object, extractor: str | None) -> None:
    outcome: DecisionGraph | CompileError
    try:
        outcome = compile_schema(schema, default_extractor=extractor)
    except CompileError as error:
        outcome = error
    if isinstance(outcome, CompileError):
        assert outcome.reasons
        return
    graph = outcome
    refusals = Refusals()
    normalise(schema, refusals)
    assert not refusals, "a graph came back from a schema the normaliser refused"
    for node in graph.nodes.values():
        assert node.id.startswith(f"{node.target}#")


decidable = st.sampled_from(
    [
        ({"type": "boolean"}, "predicate"),
        ({"enum": ["a", "b", "c"]}, "choice"),
        ({"type": "integer", "minimum": 1, "maximum": 5, "x-jevson": {"ordinal": True}}, "score"),
        ({"type": "string", "default": "x"}, None),
        ({"const": 1}, None),
        ({"type": "boolean", "default": True}, None),
    ]
)
names = st.lists(st.sampled_from(["a", "b", "c", "d", "e/f", "g~h"]), min_size=1, max_size=5, unique=True)


@st.composite
def supported(draw: st.DrawFn, depth: int = 0) -> tuple[dict[str, object], list[str]]:
    """An object schema of the supported subset, and the node ids it must compile to, in order."""
    properties: dict[str, object] = {}
    expected: list[str] = []
    for name in draw(names):
        token = name.replace("~", "~0").replace("/", "~1")
        if depth < 3 and draw(st.booleans()):
            child, below = draw(supported(depth + 1))
            properties[name] = child
            expected += [f"/{token}{i}" for i in below]
        else:
            field, role = draw(decidable)
            if field.get("type") == "boolean":  # a decided bool needs a statement; one per name
                field = {**field, "description": f"the {name} flag holds"}
            properties[name] = field
            expected += [f"/{token}#{role}"] if role else []
    return {"type": "object", "properties": properties, "required": list(properties)}, expected


@DETERMINISTIC
@given(supported())
def test_the_supported_subset_always_compiles_to_exactly_its_decidable_leaves(
    case: tuple[dict[str, object], list[str]],
) -> None:
    schema, expected = case
    nodes = compile_schema(schema).nodes.values()
    assert [node.id for node in nodes] == expected
    asked = [(node.question, node.options) for node in nodes]
    assert len(set(asked)) == len(asked), "qualified labels keep every question distinct"


refusing = st.sampled_from(
    [
        ({"type": "boolean", "description": "it holds"}, None),
        ({"enum": ["a", "b"]}, None),
        ({"const": 1}, None),
        ({"type": "string"}, "unbounded_field"),
        ({"enum": list(range(300))}, "enum_size"),
        ({"type": "object"}, "dict_field"),
        ({}, "any_field"),
        ({"type": "string", "x-jevson": {"source": {}}}, "source_selection_dropped"),
    ]
)


@st.composite
def mixed(draw: st.DrawFn, depth: int = 0, prefix: str = "") -> tuple[dict[str, object], list[tuple[str, str]]]:
    """A supported-subset object with refusing leaves mixed in, and the (pointer, reason) of each."""
    properties: dict[str, object] = {}
    bad: list[tuple[str, str]] = []
    for name in draw(st.lists(st.sampled_from("abcd"), min_size=1, max_size=4, unique=True)):
        if depth < 2 and draw(st.booleans()):
            child, below = draw(mixed(depth + 1, f"{prefix}/{name}"))
            properties[name] = child
            bad += below
        else:
            field, code = draw(refusing)
            if field.get("type") == "boolean":  # one statement per pointer keeps questions distinct
                field = {**field, "description": f"the {prefix}/{name} flag holds"}
            properties[name] = field
            bad += [(f"{prefix}/{name}", code)] if code else []
    return {"type": "object", "properties": properties, "required": list(properties)}, bad


@DETERMINISTIC
@given(mixed())
def test_refusal_names_exactly_the_refusing_leaves_and_never_returns_a_partial_graph(
    case: tuple[dict[str, object], list[tuple[str, str]]],
) -> None:
    schema, bad = case
    if not bad:
        compile_schema(schema)
        return
    with pytest.raises(CompileError) as caught:
        compile_schema(schema)
    assert sorted((r.pointer, str(r.reason)) for r in caught.value.reasons) == sorted(bad)
