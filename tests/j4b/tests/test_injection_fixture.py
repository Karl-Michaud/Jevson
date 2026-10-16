from __future__ import annotations

import ast
import random
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from tests.j4b import build_injection_fixture as B
from tests.j4b import injection as I

ROOT = Path(__file__).resolve().parents[3]


def _probe_case_and_variants(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any, random.Random]:
    """Execute the probe's own `case()` and `variants()` without its API client or its top-level run."""
    stub = types.ModuleType("jevclient")
    stub.Jev = stub.save = stub.fmt_rate = None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jevclient", stub)
    monkeypatch.setattr(sys, "path", [str(ROOT / "tests" / "probes"), *sys.path])
    monkeypatch.delitem(sys.modules, "candidates.probe_abstention", raising=False)
    tree = ast.parse((ROOT / B.PROBE).read_text())
    keep: list[ast.stmt] = [
        n
        for n in tree.body
        if isinstance(n, ast.Import | ast.ImportFrom | ast.Assign)
        or (isinstance(n, ast.Expr) and "asyncio.run" not in ast.unparse(n))
        or (isinstance(n, ast.FunctionDef) and n.name in {"case", "variants"})
    ]
    ns: dict[str, Any] = {"__file__": str(ROOT / B.PROBE)}
    exec(compile(ast.Module(body=keep, type_ignores=[]), B.PROBE, "exec"), ns)
    return ns["case"], ns["variants"], ns["R"]


def test_fixture_matches_the_probe_exactly(monkeypatch: pytest.MonkeyPatch) -> None:
    case, variants, rng = _probe_case_and_variants(monkeypatch)
    rng.seed(B.SEED)
    fixture = {c["case_id"]: c for c in I.load_fixture()}
    for i in range(20):
        before = rng.getstate()
        src, crit, claim, fail, _pas = case(i)
        after = rng.getstate()
        # case() draws the same values whatever its index, so replaying case i's draws through case(kc) yields
        # the probe's failing draft of criterion type kc for this source: the companion.
        kc = (i + 1) % 4
        rng.setstate(before)
        c_src, c_crit, _c_claim, c_fail, _c_pas = case(kc)
        assert rng.getstate() == after
        assert c_src == src
        for v, (s, d) in variants(src, fail, claim).items():
            if v == "V0":
                continue
            c = fixture[f"p7-s{i:02d}-{v}"]
            assert c["source"] == s
            assert c["drafts"][B.INJECTED_FIELD]["draft"] == d
            assert c["drafts"][B.INJECTED_FIELD]["criteria"][0]["probe_question"] == crit
            assert c["drafts"][B.COMPANION_FIELD]["draft"] == c_fail
            assert c["drafts"][B.COMPANION_FIELD]["criteria"][0]["probe_question"] == c_crit


def test_checked_in_fixture_is_the_builder_output() -> None:
    assert B.FIXTURE.read_text(encoding="utf-8") == B.dumps(B.build())


def test_counts_and_ground_truth() -> None:
    cases = I.load_fixture()
    s = B.summary(cases)
    assert (s["cases"], s["sources"]) == (80, 20)
    assert s["by_variant"] == {"V1": 20, "V2": 20, "V3": 20, "V4": 20}
    for c in cases:
        assert set(c["drafts"]) == {B.INJECTED_FIELD, B.COMPANION_FIELD}
        types_ = {spec["criterion_type"] for spec in c["drafts"].values()}
        assert len(types_) == 2  # two fields, two different criteria: no two questions alike
        for spec in c["drafts"].values():
            assert spec["truth"] == {crit["id"]: False for crit in spec["criteria"]}
        injected = c["drafts"][B.INJECTED_FIELD]["draft"]
        assert ("OVERRIDE" in c["source"]) == (c["variant"] == "V4")
        assert ("OVERRIDE" in injected) == (c["variant"] == "V3")
        assert "OVERRIDE" not in c["drafts"][B.COMPANION_FIELD]["draft"]


def test_builder_main_writes_both_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(B, "FIXTURES", tmp_path)
    monkeypatch.setattr(B, "FIXTURE", tmp_path / "f.jsonl")
    monkeypatch.setattr(B, "SUMMARY", tmp_path / "s.json")
    assert B.main() == 0
    assert (tmp_path / "f.jsonl").read_text() == B.FIXTURE.read_text() == B.dumps(B.build())
    assert '"cases": 80' in (tmp_path / "s.json").read_text()


def _all_failing(cases: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, bool]]]:
    return {c["case_id"]: {f: dict(spec["truth"]) for f, spec in c["drafts"].items()} for c in cases}


def test_regression_counts_a_flip_of_either_draft() -> None:
    cases = I.load_fixture()
    judged = _all_failing(cases)
    assert I.regression(cases, judged) == {"cases": 80, "flips": 0, "flipped": [], "max_flips": 3, "passed": True}
    for n, c in enumerate(cases[:4]):
        field = B.INJECTED_FIELD if n % 2 else B.COMPANION_FIELD
        (crit,) = judged[c["case_id"]][field]
        judged[c["case_id"]][field][crit] = True
        r = I.regression(cases, judged)
        assert r["flips"] == n + 1
        assert r["passed"] is (n + 1 <= 3)


def test_regression_refuses_missing_or_mismatched_verdicts() -> None:
    cases = I.load_fixture()
    judged = _all_failing(cases)
    del judged[cases[0]["case_id"]]
    with pytest.raises(ValueError, match="no verdicts"):
        I.regression(cases, judged)
    judged = _all_failing(cases)
    judged[cases[0]["case_id"]][B.INJECTED_FIELD] = {"other": False}
    with pytest.raises(ValueError, match="verdicts for"):
        I.regression(cases, judged)
