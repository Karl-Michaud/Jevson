"""The eight configurations of the run grid (design §1): library arm L0-L3 x criterion form F0/F1.

Every configuration names both adjudication options and `step_timeout_s` by keyword, so none of them moves if a
library default is later flipped (FEAS48-R8-3). `step_timeout_s = 630.0` in all eight, `L0` included, so the
drafting client's 615 s retry ladder is never cut by the executor's timeout (plan §11 D16, reading (a)); it
changes no request, key or decision.
"""

from __future__ import annotations

from jevson import JevsonConfig

STEP_TIMEOUT_S = 630.0

L0 = JevsonConfig(criterion_template="1.1.0", draft_screen=False, step_timeout_s=STEP_TIMEOUT_S)
"""Baseline: template 1.1.0, no screen."""
L1 = JevsonConfig(criterion_template="1.1.0", draft_screen=True, step_timeout_s=STEP_TIMEOUT_S)
"""M1: the draft screen."""
L2 = JevsonConfig(criterion_template="1.2.0", draft_screen=False, step_timeout_s=STEP_TIMEOUT_S)
"""M2: criterion template 1.2.0."""
L3 = JevsonConfig(criterion_template="1.2.0", draft_screen=True, step_timeout_s=STEP_TIMEOUT_S)
"""M1 + M2."""

LIBRARY_ARMS: dict[str, JevsonConfig] = {"L0": L0, "L1": L1, "L2": L2, "L3": L3}
FORMS = ("F0", "F1")
CONFIGURATIONS: tuple[tuple[str, str], ...] = tuple((arm, form) for arm in LIBRARY_ARMS for form in FORMS)
"""The full grid, run on the P-set and the R-set; the I-set and [P7] run under the four library arms only."""


def criterion_key(form: str) -> str:
    """The criterion text a configuration's form reads from a fixture row or field: `f0` or `f1`."""
    return {"F0": "f0", "F1": "f1"}[form]
