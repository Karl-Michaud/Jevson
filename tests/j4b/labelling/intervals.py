"""95% intervals for proportions and their differences, stdlib only.

- `wilson`: the Wilson score interval for one proportion (the interval EVIDENCE.md quotes throughout).
- `newcombe_unpaired`: Newcombe's hybrid score interval for p1 - p2 from independent samples (Newcombe 1998,
  Statistics in Medicine 17:873, method 10); `newcombe_hybrid` is its recombination step over any two intervals,
  used with `scaled` when one rate is a sampled rate times an exactly known share.
- `newcombe_paired`: Newcombe's interval for p1 - p2 from paired binary outcomes (Newcombe 1998, Statistics in
  Medicine 17:2635, method 10), with the phi correction and no continuity correction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float
    high: float


def wilson(k: int, n: int, z: float = Z95) -> Interval:
    if n <= 0 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n and n > 0, got k={k}, n={n}")
    p = k / n
    z2 = z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    # Clamp float noise: the exact bounds at k = 0 and k = n are 0 and 1.
    return Interval(p, max(0.0, centre - half), min(1.0, centre + half))


def newcombe_unpaired(k1: int, n1: int, k2: int, n2: int) -> Interval:
    return newcombe_hybrid(wilson(k1, n1), wilson(k2, n2))


def scaled(interval: Interval, factor: float) -> Interval:
    """A proportion's interval multiplied by a known constant (e.g. a sampled rate times an exact share)."""
    return Interval(interval.estimate * factor, interval.low * factor, interval.high * factor)


def newcombe_hybrid(a: Interval, b: Interval) -> Interval:
    """a - b from each proportion's own score interval (Newcombe's method 10 recombination)."""
    d = a.estimate - b.estimate
    low = d - math.sqrt((a.estimate - a.low) ** 2 + (b.high - b.estimate) ** 2)
    high = d + math.sqrt((a.high - a.estimate) ** 2 + (b.estimate - b.low) ** 2)
    return Interval(d, low, high)


def newcombe_paired(both: int, only_1: int, only_2: int, neither: int) -> Interval:
    """p1 - p2 where outcome 1 is yes in `both + only_1` pairs and outcome 2 in `both + only_2`."""
    n = both + only_1 + only_2 + neither
    a, b = wilson(both + only_1, n), wilson(both + only_2, n)
    d = a.estimate - b.estimate
    denom = (both + only_1) * (only_2 + neither) * (both + only_2) * (only_1 + neither)
    phi = 0.0 if denom == 0 else (both * neither - only_1 * only_2) / math.sqrt(denom)
    dl1, du1 = a.estimate - a.low, a.high - a.estimate
    dl2, du2 = b.estimate - b.low, b.high - b.estimate
    low = d - math.sqrt(max(0.0, dl1**2 - 2 * phi * dl1 * du2 + du2**2))
    high = d + math.sqrt(max(0.0, du1**2 - 2 * phi * du1 * dl2 + dl2**2))
    return Interval(d, low, high)
