"""Library-wide settings (DESIGN §3.5).

Deferred settings arrive with the work that uses them: the source screen and the retry budget with
class D (PLAN §9.2), entity-resolution settings post-v0 (PLAN §9.1).
"""

from __future__ import annotations

from dataclasses import dataclass


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
    transport_retries: int = 2
    max_input_tokens: int = 900_000
    """Preflight's per-request input limit: Phase 0r measured ~915k, less a margin (DESIGN §8.2)."""
    max_questions_per_request: int = 200
    union_fanout: bool = True
    """Ask a decisions-only union's branches in its discriminator's request and discard the unselected
    answers (speculative fan-out, DESIGN §3.2); False asks them one level later, after the
    discriminator. A union with a `generate` field always takes the later level. PLAN Phase 6 measured
    fan-out at about half the latency and requests, with the same values on 50/50 fixtures."""

    def __post_init__(self) -> None:
        if not 0 <= self.tie_margin_hundredths < 100:
            raise ValueError("tie_margin_hundredths must be in [0, 100)")
        if not self.step_timeout_s > 0:
            raise ValueError("step_timeout_s must be positive")
        for name in ("redraft_budget", "transport_retries"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        for name in ("max_input_tokens", "max_questions_per_request"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
