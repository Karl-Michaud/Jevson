"""PLAN Phase 8: the quickstart and every worked example run end to end on the fake backend, with
no API key, and print what their comments say; the README's quickstart block runs too."""

from __future__ import annotations

import re
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

EXPECTED = {
    "quickstart.py": [
        "{'category': 'billing', 'refund_requested': True, 'severity': 3, 'tags': ['urgent', 'churn_risk']}",
        "True True",
        "1 decision request(s);",
    ],
    "unions.py": [
        "{'disputed': False, 'method': {'speed': 'instant', 'type': 'bank'}}",
        "union_fanout=True: 1 request(s), 4 questions",
        "union_fanout=False: 2 request(s), 3 questions",
    ],
    "generative.py": [
        "{'summary': 'The customer wants their $40 refunded.'}",
        "llm+decision",
        "failed: ('mentions the refund amount stated in the source',)",
        "1 redraft; 2 LLM calls",
    ],
}


@pytest.fixture(autouse=True)
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_every_example_is_covered() -> None:
    assert {p.name for p in (ROOT / "examples").glob("*.py")} == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_runs_offline(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_path(str(ROOT / "examples" / name), run_name="__main__")
    out = capsys.readouterr().out
    for line in EXPECTED[name]:
        assert line in out


def test_readme_quickstart_runs_offline(capsys: pytest.CaptureFixture[str]) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"## Quickstart.*?```python\n(.*?)```", readme, re.S)
    assert block is not None
    exec(compile(block.group(1), "README.md", "exec", dont_inherit=True), {"__name__": "readme"})
    assert "'category': 'billing'" in capsys.readouterr().out
