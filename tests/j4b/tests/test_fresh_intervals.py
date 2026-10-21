"""H1 (ASTERION-48/-58 harness, design §4): `wilson` and `newcombe_paired` take `z` and float counts.

The DEFF-adjusted bars divide every count by the design effect before an interval is computed, and read it at
the bar's own z (design §4.2). The defaults must reproduce run 1's committed report byte for byte, as its
README's rescore command produces it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.j4b.labelling.intervals import Z95, newcombe_paired, wilson
from tests.j4b.labelling.records import key_row, label, read_jsonl
from tests.j4b.labelling.score import score

RUN1 = Path(__file__).resolve().parents[1] / "labelling" / "run1"
DETERMINISTIC = settings(derandomize=True, database=None, max_examples=300, deadline=None)


def test_rescoring_run_1_reproduces_its_report_byte_for_byte() -> None:
    sampling = json.loads((RUN1 / "sampling.json").read_text(encoding="utf-8"))
    key = [key_row(r) for r in read_jsonl(RUN1 / "key.jsonl")]
    labels = [label(r) for r in read_jsonl(RUN1 / "labels.jsonl")]
    text = json.dumps(score(key, labels, sampling), indent=1) + "\n"
    assert text == (RUN1 / "report.json").read_text(encoding="utf-8")


def test_wilson_takes_z_and_float_counts() -> None:
    assert wilson(0, 121, z=2.39397979981851).high == pytest.approx(0.0452, abs=5e-5)
    assert wilson(1, 121, z=2.39397979981851).high == pytest.approx(0.0599, abs=5e-5)
    halved, doubled = wilson(2.5, 10.0), wilson(5, 20, z=Z95 * math.sqrt(2))  # same p and same z * z / n
    assert (halved.estimate, halved.low, halved.high) == pytest.approx((doubled.estimate, doubled.low, doubled.high))
    with pytest.raises(ValueError, match="n > 0"):
        wilson(0.5, 0.0)
    with pytest.raises(ValueError, match="n > 0"):
        wilson(3.5, 3.0)


def manual_newcombe_paired(both: float, o1: float, o2: float, nei: float, z: float) -> tuple[float, float, float]:
    """Newcombe 1998 method 10, written out once more with every Wilson interval at `z`."""
    n = both + o1 + o2 + nei
    a, b = wilson(both + o1, n, z), wilson(both + o2, n, z)
    denom = (both + o1) * (o2 + nei) * (both + o2) * (o1 + nei)
    phi = 0.0 if denom == 0 else (both * nei - o1 * o2) / math.sqrt(denom)
    d = a.estimate - b.estimate
    dl1, du1, dl2, du2 = a.estimate - a.low, a.high - a.estimate, b.estimate - b.low, b.high - b.estimate
    low = d - math.sqrt(max(0.0, dl1**2 - 2 * phi * dl1 * du2 + du2**2))
    high = d + math.sqrt(max(0.0, du1**2 - 2 * phi * du1 * dl2 + dl2**2))
    return d, low, high


@DETERMINISTIC
@given(
    st.tuples(*[st.integers(0, 2000).map(lambda c: c / 7) for _ in range(4)]).filter(lambda t: sum(t) > 0),
    st.sampled_from([Z95, 2.3519568, 2.3939798, 2.4977055, 2.8727758]),
)
def test_newcombe_paired_passes_z_to_both_wilson_intervals(counts: tuple[float, ...], z: float) -> None:
    interval = newcombe_paired(*counts, z=z)
    assert (interval.estimate, interval.low, interval.high) == pytest.approx(manual_newcombe_paired(*counts, z=z))


def test_newcombe_paired_defaults_to_95_percent() -> None:
    assert newcombe_paired(3, 7, 2, 40) == newcombe_paired(3, 7, 2, 40, z=Z95)
    assert newcombe_paired(3, 7, 2, 40).high < newcombe_paired(3, 7, 2, 40, z=2.8727758).high
