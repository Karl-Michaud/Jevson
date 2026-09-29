"""Per-probe scoring (PLAN Phase 0), including ties.

Probabilities are integer hundredths (DESIGN §2.1). A choice whose top two options differ by <= 10 hundredths
is a tie (DESIGN §6.2); a tie counts as not correct (probe 1), not abstaining (probe 2), and not a false
abstention (probe 3). A distribution outside the sum tolerance, missing or extra options, a value outside
[0, 1], or a vendor ``choice`` naming a non-argmax option outside the tie band is an invalid answer.
Entity pairs use a plain 0.5 boundary (DESIGN §5.7); the source screen flags at p >= 0.56 (DESIGN §5.8),
and an invalid screen answer counts as flagged.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping, Sequence

NONE = "none_of_these"
TIE_MARGIN = 10          # hundredths, DESIGN §6.2
NOUL_TRUE_MIN = 56       # hundredths: true iff p >= 0.56, false iff p <= 0.44 (DESIGN §4.2)
NOUL_FALSE_MAX = 44
SCREEN_FLAG_MIN = 56     # DESIGN §5.8
PAIR_SAME_ABOVE = 50     # an edge iff p(same) > 0.5 (DESIGN §5.7)

Status = Literal["ok", "tie", "invalid"]


def hundredths(x: object) -> int:
    """A probability as integer hundredths; raises ValueError for anything that is not a number in [0, 1]."""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or math.isnan(x) or not 0 <= x <= 1:
        raise ValueError(f"not a probability: {x!r}")
    return round(x * 100)


def sum_tolerance(k: int) -> int:
    """min(ceil(K/2), 5) hundredths (DESIGN §2.1)."""
    return min(math.ceil(k / 2), 5)


@dataclass(frozen=True)
class ChoiceAnswer:
    status: Status
    selected: str | None          # argmax option (None only when invalid)
    dist: Mapping[str, int]       # hundredths per offered option (empty when invalid)
    margin: int | None            # top-two difference in hundredths
    reason: str | None = None     # why invalid


def decode_choice(answer: object, offered: Sequence[str], tie_margin: int = TIE_MARGIN) -> ChoiceAnswer:
    if len(offered) < 2 or len(set(offered)) != len(offered):
        raise ValueError("a choice needs at least two distinct options")
    bad = lambda why: ChoiceAnswer("invalid", None, {}, None, why)  # noqa: E731
    if not isinstance(answer, Mapping):
        return bad("answer is not an object")
    probs = answer.get("probabilities")
    if not isinstance(probs, Mapping):
        return bad("no probabilities")
    if set(probs) != set(offered):
        return bad("options differ from those offered")
    try:
        dist = {o: hundredths(probs[o]) for o in offered}
    except ValueError:
        return bad("probability outside [0, 1] or not a number")
    if abs(sum(dist.values()) - 100) > sum_tolerance(len(offered)):
        return bad("sum outside tolerance")
    ranked = sorted(offered, key=lambda o: (-dist[o], offered.index(o)))
    margin = dist[ranked[0]] - dist[ranked[1]]
    if margin <= tie_margin:
        return ChoiceAnswer("tie", ranked[0], dist, margin)
    vendor = answer.get("choice")
    if vendor is not None and vendor != ranked[0]:
        return ChoiceAnswer("invalid", None, dist, margin, "vendor choice is not the argmax")
    return ChoiceAnswer("ok", ranked[0], dist, margin)


def decode_noul(answer: object) -> tuple[Status, bool | None, int | None]:
    """(status, value, p in hundredths) under the bool rule with the tie margin."""
    if not isinstance(answer, Mapping) or "noul" not in answer:
        return "invalid", None, None
    try:
        p = hundredths(answer["noul"])
    except ValueError:
        return "invalid", None, None
    if p >= NOUL_TRUE_MIN:
        return "ok", True, p
    if p <= NOUL_FALSE_MAX:
        return "ok", False, p
    return "tie", None, p


def pair_probability(answer: object) -> int | None:
    """p(same) in hundredths for an entity pair noul, or None if the answer is invalid."""
    if not isinstance(answer, Mapping) or "noul" not in answer:
        return None
    try:
        return hundredths(answer["noul"])
    except ValueError:
        return None


def screen_flagged(answer: object) -> bool:
    if not isinstance(answer, Mapping) or "noul" not in answer:
        return True
    try:
        return hundredths(answer["noul"]) >= SCREEN_FLAG_MIN
    except ValueError:
        return True


# ---------------------------------------------------------------- candidate selection (probes 1-3, 6, 8)

Outcome = Literal["correct", "partial", "wrong", "abstain", "tie", "invalid"]


def classify(decoded: ChoiceAnswer, labels: Mapping[str, str]) -> Outcome:
    """labels: option id -> "correct" | "partial" | "wrong" for every candidate option."""
    if decoded.status == "invalid":
        return "invalid"
    if decoded.status == "tie":
        return "tie"
    if decoded.selected == NONE:
        return "abstain"
    lab = labels[decoded.selected]
    if lab not in ("correct", "partial", "wrong"):
        raise ValueError(f"unknown label {lab!r}")
    return lab  # type: ignore[return-value]


@dataclass(frozen=True)
class Counts:
    n: int
    correct: int
    abstain: int
    tie: int
    invalid: int
    partial: int
    wrong: int

    @classmethod
    def of(cls, outcomes: Iterable[Outcome]) -> "Counts":
        o = list(outcomes)
        return cls(len(o), o.count("correct"), o.count("abstain"), o.count("tie"), o.count("invalid"),
                   o.count("partial"), o.count("wrong"))


def probe1_k(c: Counts) -> int:
    """Correct span chosen; a tie is not correct."""
    return c.correct


def probe2_k(c: Counts) -> int:
    """none_of_these chosen on absent-answer cases; a tie is not abstaining."""
    return c.abstain


def probe3_k(c: Counts) -> int:
    """none_of_these chosen on present-answer cases (false abstention); a tie is not a false abstention."""
    return c.abstain


# ---------------------------------------------------------------- entity resolution (probe 4)

ComponentKind = Literal["correct", "unresolved", "merge", "split"]
Pairs = Mapping[tuple[int, int], int]   # (i, j) with i < j -> p(same) in hundredths


def components(n: int, pairs: Pairs) -> list[tuple[int, ...]]:
    """Connected components of the mentions over pairs with p(same) > 0.5, sorted by first member."""
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for (i, j), p in pairs.items():
        if p > PAIR_SAME_ABOVE:
            parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted(tuple(g) for g in groups.values())


def _p(pairs: Pairs, a: int, b: int) -> int:
    return pairs[(a, b) if a < b else (b, a)]


def score_cluster(gold: Sequence[str], pairs: Pairs, floor: int,
                  variant: Literal["internal", "cross"]) -> list[tuple[ComponentKind, tuple[int, ...]]]:
    """Component outcomes for one cluster (DESIGN §5.7).

    gold[i] is the gold entity of mention i; every mention is a member. ``floor`` is conflict_floor in
    hundredths. Internal rule: a component with an internal pair <= floor is unresolved. Cross variant:
    additionally, a component linked to another by a pair in (floor, 50] is unresolved. Otherwise a component
    equal to a gold entity is correct, one spanning several gold entities a merge, and a proper subset of one
    gold entity a split."""
    n = len(gold)
    expected = {(i, j) for i, j in itertools.combinations(range(n), 2)}
    if set(pairs) != expected:
        raise ValueError("pairs must cover every mention pair exactly once, keyed (i, j) with i < j")
    comps = components(n, pairs)
    members_of: dict[str, set[int]] = {}
    for i, e in enumerate(gold):
        members_of.setdefault(e, set()).add(i)
    out: list[tuple[ComponentKind, tuple[int, ...]]] = []
    for c in comps:
        internal = any(_p(pairs, a, b) <= floor for a, b in itertools.combinations(c, 2))
        cross = variant == "cross" and any(
            floor < _p(pairs, a, b) <= PAIR_SAME_ABOVE for d in comps if d != c for a in c for b in d)
        if internal or cross:
            out.append(("unresolved", c))
            continue
        ents = {gold[i] for i in c}
        if len(ents) > 1:
            out.append(("merge", c))
        elif set(c) == members_of[next(iter(ents))]:
            out.append(("correct", c))
        else:
            out.append(("split", c))
    return out


def pair_accuracy(gold: Sequence[str], pairs: Pairs) -> tuple[int, int]:
    """(pairs judged correctly at the 0.5 boundary, pairs)."""
    ok = sum((p > PAIR_SAME_ABOVE) == (gold[i] == gold[j]) for (i, j), p in pairs.items())
    return ok, len(pairs)


def non_transitive_triples(n: int, pairs: Pairs) -> tuple[int, int]:
    """(triples with exactly two 'same' edges, triples)."""
    bad = tot = 0
    for a, b, c in itertools.combinations(range(n), 3):
        s = (_p(pairs, a, b) > PAIR_SAME_ABOVE) + (_p(pairs, b, c) > PAIR_SAME_ABOVE) + (_p(pairs, a, c) > PAIR_SAME_ABOVE)
        tot += 1
        bad += s == 2
    return bad, tot


def clique_complete(gold: Sequence[str], pairs: Pairs) -> tuple[int, int]:
    """(gold entities with >= 2 mentions whose every internal pair is > 0.5, such entities)."""
    ents: dict[str, list[int]] = {}
    for i, e in enumerate(gold):
        ents.setdefault(e, []).append(i)
    multi = [m for m in ents.values() if len(m) >= 2]
    full = sum(all(_p(pairs, a, b) > PAIR_SAME_ABOVE for a, b in itertools.combinations(m, 2)) for m in multi)
    return full, len(multi)


def pair_flips(run_a: Pairs, run_b: Pairs) -> tuple[int, int]:
    """(pairs whose > 0.5 decision differs between two runs, pairs)."""
    if set(run_a) != set(run_b):
        raise ValueError("runs cover different pairs")
    return sum((run_a[k] > PAIR_SAME_ABOVE) != (run_b[k] > PAIR_SAME_ABOVE) for k in run_a), len(run_a)
