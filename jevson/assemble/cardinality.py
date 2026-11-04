"""Multi-label enum arrays: per-value membership outcomes -> one array (DESIGN §4.2, §6.1, R8).

The executor keeps each membership predicate's outcome under its node id. `fold` turns each array's
outcomes into what the assembler takes:

- accepted values (`True`) in declared enum order, whatever their probabilities' order, so
  `uniqueItems` holds by construction;
- `maxItems` keeps the first k in that order, and the rest go to one `Overflow` with their membership
  probabilities: overflow is never silently discarded (R8);
- each tied, refused, invalid or over-budget membership is one `Unresolved` at the array pointer
  naming the value (an array hole), and the other values are still emitted;
- an array none of whose values was decided is not emitted, only its holes; members that were
  never asked because their union branch did not resolve give one
  `Unresolved(dependency_unresolved)` and no array.

An unmet `minItems` is left to final validation, which reports it as a `Violation`: never padded.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from jevson.assemble.assembler import Committed, Outcome
from jevson.types import DecidedBy, Decision, DecisionNode, JSONValue, Overflow, Unresolved, UnresolvedReason


def fold(
    nodes: Iterable[DecisionNode], outcomes: Mapping[str, Outcome], decisions: Mapping[str, Decision]
) -> tuple[list[Outcome], tuple[Unresolved, ...], tuple[Overflow, ...]]:
    """The outcomes with each array's members folded into it, the array holes, and the overflow."""
    arrays: dict[str, list[DecisionNode]] = {}
    for node in nodes:
        if node.member is not None and node.id in outcomes:
            arrays.setdefault(node.target, []).append(node)
    members = {node.id for group in arrays.values() for node in group}
    folded = [outcome for key, outcome in outcomes.items() if key not in members]
    holes: list[Unresolved] = []
    overflow: list[Overflow] = []
    for pointer, group in arrays.items():
        if pointer in outcomes:
            continue  # a union at the array's own pointer did not resolve, and is the hole already
        results = [outcomes[node.id] for node in group]
        if all(isinstance(r, Unresolved) and r.reason is UnresolvedReason.DEPENDENCY_UNRESOLVED for r in results):
            holes.append(Unresolved(pointer, UnresolvedReason.DEPENDENCY_UNRESOLVED))
            continue
        holes += [
            Unresolved(pointer, r.reason, detail=f"membership of {n.member!r}")
            for n, r in zip(group, results, strict=True) if isinstance(r, Unresolved)
        ]  # fmt: skip
        if all(isinstance(r, Unresolved) for r in results):
            continue  # no value was decided, so no array is emitted
        accepted = [n for n, r in zip(group, results, strict=True) if isinstance(r, Committed) and r.value is True]
        limit = group[0].max_items
        kept, dropped = (accepted, []) if limit is None else (accepted[:limit], accepted[limit:])
        value: list[JSONValue] = [n.member for n in kept]
        folded.append(Committed(pointer, value, DecidedBy.DECISION))
        if dropped:
            probabilities = tuple(decisions[f"{n.id}@0"].distribution_hundredths["true"] for n in dropped)
            overflow.append(Overflow(pointer, (), probabilities, tuple(n.member for n in dropped)))
    return folded, tuple(holes), tuple(overflow)
