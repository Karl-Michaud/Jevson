"""Pre-registered constants of the Phase 0 decision rules (docs/taxonomy.md §2). Changing any of these after
the first live call is allowed only as a recorded bug fix (docs/taxonomy.md §2.12)."""
from __future__ import annotations

MODEL = "jev-1.13.0"
SEED = 20260929

# probes 1-3
N_TARGET = 150                       # per probe (probe 3 shares probe 1's cases)
MIN_COMPETITORS = 3                  # non-correct options beside the correct one (probe 1), remaining options (probe 2)
MAX_OPTIONS = 50                     # DESIGN §5.3 default max_candidates, counted after occurrence expansion
MAX_CASES_PER_DOC = 8                # per probe
MIN_HARD_SHARE = 0.30                # of the probe 1-3 cases: long multi-entity documents or superseded values
MIN_REPEATED_PRESENT = 20            # present cases whose correct text occurs at more than one offset
HARD_MIN_DOC_CHARS = 4000
MAX_DOC_CHARS = 40000

# probe 4
N_CLUSTERS = 50
MIN_MENTIONS, MAX_MENTIONS = 4, 14
PROBE4_RUNS = ("A", "B")
PROBE4_MAX_PER_DOMAIN = 40          # amended from 12 (then 25) before any Jev call (docs/taxonomy.md §2.12)
PROBE4_MAX_PER_DOC = 2

# probe 5: IDX-320 = indexed into the full 320-list in one request; KEY-320 = keyed, one request
P5_REPRODUCE_IDX_MIN = 0.20
P5_KEY_MAX = 0.02
P5_INDEXED_FINE_MAX = 0.02

# probes 6 and 8
N_PROBE6 = 50
N_PROBE8 = 50
CALIBRATION_BINS = 15
BOOTSTRAP_REPLICATES = 2000

# probe 9 (the second gate, docs/gate-probe.md)
GATE_PASS_MIN = 56                   # hundredths: a verification noul passes iff p >= 0.56 (the bool rule; ties fail)
GATE_WRONG_MAX = 0.05                # proceed needs committed-when-absent and wrong-when-present <= 0.05
GATE_DROP_WRONG = 0.10               # drop source selection if committed-when-absent > 0.10
GATE_CORRECT_MIN = 0.70              # ... or correct commits < 0.70 (probe 1's stop line)

# budget
MAX_REQUESTS = 5000
RATE_PER_MIN = 1000                  # below the vendor's ~1,200/min

# joint (p_correct, p_abstain_present) points for the probes 1+3 operating characteristic
JOINT_POINTS = ((0.88, 0.07), (0.85, 0.10), (0.85, 0.05), (0.78, 0.20), (0.80, 0.10), (0.75, 0.15),
                (0.70, 0.10), (0.70, 0.20), (0.72, 0.18))
ABANDON_POINTS = ((0.85, 0.10, 0.80), (0.85, 0.10, 0.60), (0.80, 0.15, 0.70), (0.75, 0.15, 0.65),
                  (0.70, 0.20, 0.60), (0.70, 0.10, 0.80))
PROBE4_POINTS = ((0.90, 0.02), (0.85, 0.05), (0.85, 0.03), (0.80, 0.03), (0.70, 0.05), (0.70, 0.03),
                 (0.90, 0.06))
PROBE4_OC_NS = (120, 240)
