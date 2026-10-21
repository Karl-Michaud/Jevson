"""H17: a full fake attempt (every set, all eight configurations) through the metered path completes, does not
void, and replays from its records with zero misses; every first-draft request of every configuration has a
`replay_key` among the drafting phase's recorded keys (design §2.3, §6.2; FEAS48-R8-1, FEAS48-R8-5)."""

from __future__ import annotations

import json
from pathlib import Path

from jevson.execute.drafting import TOOL_SCHEMA, messages
from jevson.llm.replay import replay_key
from tests.integration.openai_chat import MODEL
from tests.j4b.fresh import arms, phases, runner, workload
from tests.j4b.fresh.attempts import Attempts
from tests.j4b.fresh.spend import SpendLedger
from tests.j4b.tests import fake_api


def test_h17_every_configurations_first_draft_keys_are_the_drafting_phases() -> None:
    for phase in ("dev", "confirm"):
        w = workload.load(phase)
        recorded = phases.first_keys(w)
        assert len(recorded) == sum(len(w.fields[d.domain]) for d in w.documents.values())
        for config in arms.CONFIGURATIONS:
            keys = {
                replay_key(MODEL, messages(drafting, doc.text, None), TOOL_SCHEMA)
                for doc in w.documents.values()
                for drafting in phases.draftings(w.fields[doc.domain], config)
            }
            assert keys == recorded, config


def test_h17_a_full_fake_attempt_completes_and_replays_with_zero_misses(tmp_path: Path) -> None:
    api = fake_api.FakeAPI()
    e, _ = fake_api.env(tmp_path / "fresh", api, load=workload.load)
    assert runner.run_phase(e, "dev", 1) == 0
    assert runner.run_phase(e, "confirm", 1) == 0
    a = Attempts(e.root)
    assert a.complete(1)
    assert a.void(1) is None
    ledger = SpendLedger(e.root)
    assert {(s.endpoint, s.model) for s in ledger.settles()} == {
        ("decisions", fake_api.DECISION_MODEL),
        ("chat", fake_api.CHAT_MODEL),
    }
    calls = dict(api.calls)
    w = workload.load("confirm")
    replayed = runner.outcomes_of(w, a.phase_dir(1, "confirm"), partial=False)
    assert api.calls == calls  # nothing was sent
    assert len(replayed) == sum(len(us) for us in w.units.values())
    assert {u.set_name for u in replayed} == {"iset", "p7", "pset", "rset"}
    assert {u.config for u in replayed if u.set_name in ("pset", "rset")} == set(arms.CONFIGURATIONS)
    complete = json.loads((a.phase_dir(1, "confirm") / "complete.json").read_text())
    assert complete["units"] == len(replayed)
