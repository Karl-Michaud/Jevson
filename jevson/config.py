"""Library-wide settings (DESIGN §3.5).

Deferred settings arrive with the work that uses them: the source screen and the retry budget with
class D (PLAN §9.2), entity-resolution settings post-v0 (PLAN §9.1). Transport retries are not here:
they belong to the backend that makes the requests, `DecisionsBackend(transport_retries=...)`.

The opt-in adjudication default is a module constant, the one source `compile_schema` and
`JevsonConfig` both read. This module imports nothing from `jevson`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

CriterionTemplate = Literal["1.1.0", "1.2.0"]
"""The criterion template versions (DESIGN §5.2); `compile/questions.py` holds their texts."""
DEFAULT_CRITERION_TEMPLATE: CriterionTemplate = "1.1.0"


@dataclass(frozen=True)
class JevsonConfig:
    """Per-instance settings. In v0 a `default_extractor` makes an unbounded string field refuse with
    `source_selection_dropped` instead of `unbounded_field`: nothing is selected from the source."""

    model: str = "gpt-6-luna"
    """The model every decision request names; the API offers no snapshot, so the returned `model`
    string is recorded too (DESIGN §2, R15)."""
    tie_margin_hundredths: int = 10
    """A committing decision whose top two outcomes differ by at most this is a tie (DESIGN §6.2)."""
    default_extractor: str | None = None
    raise_on_unresolved_required: bool = False
    step_timeout_s: float = 120.0
    redraft_budget: int = 1
    max_input_tokens: int = 900_000
    """Preflight's per-request input limit: Phase 0r measured ~915k, less a margin (DESIGN §8.2)."""
    max_questions_per_request: int = 200
    union_fanout: bool = True
    """Ask a decisions-only union's branches in its discriminator's request and discard the unselected
    answers (speculative fan-out, DESIGN §3.2); False asks them one level later, after the
    discriminator. A union with a `generate` field always takes the later level. PLAN Phase 6 measured
    fan-out at about half the latency and requests, with the same values on 50/50 fixtures."""
    criterion_template: CriterionTemplate = DEFAULT_CRITERION_TEMPLATE
    """The criterion template every criterion question uses (DESIGN §5.2), recorded as
    `versions["criterion_template"]`. Experimental: `"1.2.0"` is opt-in until the ASTERION-48/-58
    measurement."""

    def __post_init__(self) -> None:
        if not 0 <= self.tie_margin_hundredths < 100:
            raise ValueError("tie_margin_hundredths must be in [0, 100)")
        if not self.step_timeout_s > 0:
            raise ValueError("step_timeout_s must be positive")
        if self.redraft_budget < 0:
            raise ValueError("redraft_budget must be >= 0")
        for name in ("max_input_tokens", "max_questions_per_request"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.criterion_template not in get_args(CriterionTemplate):
            raise ValueError(f"criterion_template must be one of {', '.join(get_args(CriterionTemplate))}")
