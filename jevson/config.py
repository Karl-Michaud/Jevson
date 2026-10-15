"""Library-wide settings (DESIGN §3.5).

Deferred settings arrive with the work that uses them: the source screen and the retry budget with
class D (PLAN §9.2), entity-resolution settings post-v0 (PLAN §9.1).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JevsonConfig:
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
