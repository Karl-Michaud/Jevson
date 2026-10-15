"""Over generated schemas, normalisation returns a whole tree or raises `CompileError` (PLAN Phase 2).

Never a partial result, never another exception. The generator mixes valid constructs with every
keyword the normaliser treats specially, and with values of the wrong JSON type.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from jevson.compile.normalise import Kind, SchemaNode, normalise, normalise_schema
from jevson.compile.refusal import Refusals
from jevson.errors import CompileError

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=400)

scalars = st.one_of(st.none(), st.booleans(), st.integers(-3, 3), st.sampled_from(["a", "b", "null", "#", ""]))
types = st.sampled_from(["string", "number", "integer", "boolean", "null", "object", "array", "decimal", "date"])
refs = st.sampled_from(["#", "#/$defs/A", "#/$defs/B", "#/$defs/Missing", "other.json", "#/$defs/A/properties/x"])
declarations = st.one_of(
    scalars,
    st.fixed_dictionaries(
        {},
        optional={
            "question": st.sampled_from(["q", "", 1]),
            "ordinal": st.sampled_from([True, False, "yes"]),
            "order": st.sampled_from(["source", "semantic", "x"]),
            "source": st.sampled_from([{}, {"extractor": "llm"}, "x"]),
            "generate": st.sampled_from([{}, {"criteria": ["c"]}, {"criteria": "c"}, {"nope": 1}, "g"]),
            "bogus": scalars,
        },
    ),
)


def schemas(children: st.SearchStrategy[object]) -> st.SearchStrategy[object]:
    keyword_values: dict[str, st.SearchStrategy[object]] = {
        "type": st.one_of(types, st.lists(types, max_size=3), scalars),
        "properties": st.one_of(st.dictionaries(st.sampled_from(["x", "y", "a/b"]), children, max_size=3), scalars),
        "required": st.one_of(st.lists(st.sampled_from(["x", "y", "z"]), max_size=3), scalars),
        "items": st.one_of(children, st.lists(children, max_size=2)),
        "prefixItems": st.lists(children, max_size=2),
        "additionalProperties": st.one_of(st.booleans(), children),
        "enum": st.one_of(st.lists(scalars, max_size=4), scalars),
        "const": scalars,
        "anyOf": st.one_of(st.lists(children, max_size=3), scalars),
        "oneOf": st.lists(children, max_size=3),
        "allOf": st.one_of(st.lists(children, max_size=3), scalars),
        "discriminator": st.just({"propertyName": "x"}),
        "$ref": st.one_of(refs, scalars),
        "$dynamicRef": st.just("#m"),
        "x-jevson": declarations,
        "format": st.sampled_from(["binary", "date", "email"]),
        "pattern": st.just("^a"),
        "maximum": st.integers(0, 3),
        "default": scalars,
        "not": children,
    }
    dicts = st.fixed_dictionaries({}, optional=keyword_values)
    return st.one_of(scalars, dicts)


nested = st.recursive(st.one_of(scalars, st.just({}), st.just({"type": "boolean"})), schemas, max_leaves=12)
roots = st.builds(
    lambda root, a, b: {**root, "$defs": {"A": a, "B": b}} if isinstance(root, dict) else root,
    schemas(nested),
    nested,
    nested,
)


def refused_anywhere(node: SchemaNode) -> bool:
    children = [sub for _, sub in node.properties] + ([node.items] if node.items else [])
    return node.kind is Kind.REFUSED or any(refused_anywhere(c) for c in children)


@DETERMINISTIC
@given(roots)
def test_normalisation_returns_a_whole_tree_or_raises_compile_error(schema: object) -> None:
    outcome: SchemaNode | CompileError
    try:
        outcome = normalise_schema(schema)
    except CompileError as error:
        outcome = error
    if isinstance(outcome, CompileError):
        assert outcome.reasons
    else:
        assert not refused_anywhere(outcome)


@DETERMINISTIC
@given(roots)
def test_every_refused_subtree_is_explained_by_a_refusal(schema: object) -> None:
    refusals = Refusals()
    root = normalise(schema, refusals)
    assert not refused_anywhere(root) or refusals
