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

from jevson import CompileError, JevsonConfig, RefusalCode, compile_schema
from jevson.assemble.validation import validator
from jevson.checks import CheckRule
from jevson.compile.normalise import normalise
from jevson.compile.refusal import Refusals
from jevson.graph import DecisionGraph
from jevson.types import DecisionKind, DecisionNode, StepNode
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


STEPS = [1e-320, 1e-30, 0.1, 0.3, 0.7, 1, 2, 2.5, 7, 1e300]


@DETERMINISTIC
@given(st.integers(-30, 30), st.integers(0, 40), st.sampled_from(STEPS))
def test_an_ordinal_compiles_to_exactly_the_levels_final_validation_accepts(low: int, span: int, step: float) -> None:
    # Tiny and huge `multipleOf` included: 1e-30 broke a 28-digit decimal context, 1e-320 overflows in jsonschema.
    keywords = {"type": "integer", "minimum": low, "maximum": low + span, "multipleOf": step}
    accepted = tuple(v for v in range(low, low + span + 1) if validator(keywords).is_valid(v))
    schema = {"type": "object", "properties": {"r": {**keywords, "x-jevson": {"ordinal": True}}}, "required": ["r"]}
    if not 2 <= len(accepted) <= 10:
        with pytest.raises(CompileError) as caught:
            compile_schema(schema)
        assert [r.reason for r in caught.value.reasons] == [RefusalCode.ORDINAL_LEVELS]
        return
    assert compile_schema(schema).nodes["/r#score"].values == accepted


# --- the opt-in adjudication options (DESIGN §5.2, §6.3; ASTERION-48) --------------------------------

criteria_lists = st.lists(
    st.sampled_from(["names the amount", "is one sentence", "is polite"]), max_size=3, unique=True
)
rubrics = st.sampled_from(
    [None, {"description": "how faithful it is", "levels": ["poor", "ok", "good"], "minimum": "ok"}]
)


@st.composite
def generative(draw: st.DrawFn, depth: int = 0) -> dict[str, object]:
    """An object schema whose leaves mix decidable fields and generative fields with zero to three
    criteria and an optional rubric, nested up to two levels."""
    properties: dict[str, object] = {}
    for name in draw(names):
        if depth < 2 and draw(st.booleans()):
            properties[name] = draw(generative(depth + 1))
        elif draw(st.booleans()):
            generate: dict[str, object] = {"criteria": draw(criteria_lists)}
            rubric = draw(rubrics)
            if rubric is not None:
                generate["rubric"] = rubric
            properties[name] = {"type": "string", "x-jevson": {"generate": generate}}
        else:
            field, _ = draw(decidable)
            if field.get("type") == "boolean":
                field = {**field, "description": f"the {name} flag holds"}
            properties[name] = field
    return {"type": "object", "properties": properties, "required": list(properties)}


def compiled(schema: object, **options: object) -> DecisionGraph | str:
    try:
        return compile_schema(schema, **options)  # type: ignore[arg-type]
    except CompileError as error:
        return str(error)


def shape(graph: DecisionGraph | str) -> object:
    """A graph's ids, questions and dependencies, or the refusal it raised."""
    if isinstance(graph, str):
        return graph
    return [(n.id, getattr(n, "question", None), sorted(n.dependencies)) for n in graph.nodes.values()]


@DETERMINISTIC
@given(st.one_of(roots, generative()))
def test_the_default_options_compile_the_graph_the_config_defaults_name(schema: object) -> None:
    config = JevsonConfig()
    explicit = compiled(schema, criterion_template=config.criterion_template)
    assert shape(compiled(schema)) == shape(explicit)


@DETERMINISTIC
@given(generative(), st.sampled_from(["1.1.0", "1.2.0"]))
def test_every_check_names_a_node_of_the_kind_its_rule_judges(schema: object, template: str) -> None:
    graph = compile_schema(schema, criterion_template=template)
    kinds = {CheckRule.RUBRIC: DecisionKind.SCORE, CheckRule.CRITERION: DecisionKind.PREDICATE}
    for step in graph.nodes.values():
        if not isinstance(step, StepNode) or step.drafting is None:
            continue
        for check in step.drafting.checks:
            node = graph.nodes[check.node_id]
            assert isinstance(node, DecisionNode)
            assert node.kind is kinds[check.rule]
            assert step.id in node.dependencies
