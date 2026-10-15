"""`compile_schema()`: a schema → a `DecisionGraph`, or one `CompileError` naming every problem (R14).

Standalone and network-free: normalising, mapping, and graph construction never call a backend,
an extractor, or an LLM, so every refusal happens before anything is spent.
"""

from __future__ import annotations

from collections.abc import Set

from jevson.compile.mapping import map_tree
from jevson.compile.normalise import normalise
from jevson.compile.refusal import Refusals
from jevson.graph import DecisionGraph


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
    refusals.raise_if_any()
    return DecisionGraph(nodes)
