"""The committed pre-registration says what the frozen code does (B10 review rounds 1 and 2: STATS48-B10-2 ... -6,
RC1-2, RC1-3, RC1-4, ARCH48-B10-1, ARCH48-B10-6, ARCH48-R2-2). The document is binding, so a statement in it that
contradicts the code, or a claim about its own commit that is not true, is a defect of the pre-registration."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from tests.j4b.fresh import bar_inputs, grading, pins, report, rules, sources, truth

ROOT = Path(__file__).resolve().parents[3]
PREREG = ROOT / pins.APPENDIX


@pytest.fixture(scope="module")
def text() -> str:
    if not PREREG.exists():
        pytest.skip("no pre-registration at this commit")
    return PREREG.read_text(encoding="utf-8")


def section(text: str, letter: str) -> str:
    match = re.search(rf"^## {letter}\. .*?(?=^## [A-Z]\. |\Z)", text, re.DOTALL | re.MULTILINE)
    assert match, letter
    return match.group(0)


def test_stats48_b10_2_appendix_h_states_the_z_each_bar_uses_in_rules(text: str) -> None:
    h = section(text, "H")
    assert f"`inv_cdf(1 - 0.025/3)` = {rules.Z_48:.6f}" in h
    assert rules.Z_STRATA == rules.Z_48
    assert f"`inv_cdf(1 - 0.025/4)` = {rules.Z_58T:.6f} for FRR-T only" in h
    assert f"`inv_cdf(1 - 0.025)` = {rules.Z_ONE:.6f} for the ASTERION-58 single guards (FA-NI, SC-FA, C-NI, B-NI)" in h
    assert "and the shipped-cell bars (FA-S, SC-S)" in h
    ni = rules.NI_MULTIPLIER
    assert f"({ni * rules.Z_48:.4f} and {ni * rules.Z_ONE:.4f} are displays)" in h
    assert f"{ni * rules.Z_58T:.4f}" not in h


def test_stats48_b10_5_appendix_d_quotes_the_template_versioning_sentence_of_the_design(text: str) -> None:
    sentence = next(
        line for line in (ROOT / "docs/taxonomy.md").read_text(encoding="utf-8").splitlines()
        if "the draft screen's rejection text, or the draft screen's fail threshold bumps" in line
    )  # fmt: skip
    assert sentence in section(text, "D")


def test_stats48_b10_4_appendix_o_quotes_the_frozen_definitions(text: str) -> None:
    o = section(text, "O")
    for obj in (sources.kind, sources.RENDERINGS, truth.guard, truth.occurs, truth.stated, grading.secondaries):
        assert inspect.getsource(obj) in o, obj
    for module in (bar_inputs, report):
        assert inspect.getsource(module) in o, module
    assert "_NUMBER_WORDS = [" in o
    assert "GUARDED = frozenset(" in o


def test_rc1_4_the_dry_run_figures_are_put_to_karl_not_approved(text: str) -> None:
    i = section(text, "I")
    assert "approved on" not in i
    assert "The dry-run figures put to Karl for approval" in i


def test_rc1_2_the_record_does_not_claim_the_cited_scripts_were_committed(text: str) -> None:
    n = section(text, "N")
    assert "**Item 6 was not carried out.**" in n
    assert "none of the cited script or output files survives" in section(text, "M")


def test_arch48_b10_6_d21_and_d6_are_attributed_as_they_were_decided(text: str) -> None:
    lines = section(text, "L")
    assert "recorded with the calls of item 11" not in lines
    assert "recorded with the item 11 calls" not in lines
    assert "an orchestrator call under OWNER-DECISIONS item 10, recorded in this pre-registration itself" in lines
    assert "D6 follows the binding design (both endpoints void) and departs from OWNER-DECISIONS item 11" in lines


def test_arch48_b10_1_appendix_g_says_the_canary_is_partial(text: str) -> None:
    g = section(text, "G")
    assert "**The B9 canary is partial at this commit.**" in g
    assert "a grader-file fix makes a new pre-registration" in g


def test_stats48_b10_3_appendix_c_names_every_frozen_function_and_b_corrects_the_transport_sentence(
    text: str,
) -> None:
    """Round 2: `complete` and phases' arm, form, drafting and unit code are frozen; Appendix C names each one, and
    Appendix B's verbatim plan sentence ("the transport it is handed is the amendable modules above") is corrected
    beside it, since the amendable modules now supply only the client and recording wiring."""
    c, b = section(text, "C"), section(text, "B")
    for path, names in pins.FROZEN_FUNCTIONS.items():
        listed = c.split(f"`{path}`: ", 1)[1].split(";", 1)[0].split(". ", 1)[0]
        assert [n.strip(" `") for n in listed.split(",")] == list(names), path
    assert "the transport it is handed is the amendable modules above" in b
    assert "**Correction to the sentence above (STATS48-B10-3, round 2).**" in b
    for name in ("`OpenAIChatLLM.complete`", "`run_unit`", "`FirstDraftGate`"):
        assert name in b, name


def test_rc1_3_appendix_g_names_the_advisor_server_tool_and_the_audit_refuses_it(text: str) -> None:
    g = section(text, "G")
    assert "`advisor`" in g
    assert "`server_tool_use`" in g
    assert "`grading_audit` fails a chunk on any assistant block other than text, thinking or `tool_use`" in g


def test_arch48_r2_2_appendix_g_states_the_canary_cause_as_a_hypothesis(text: str) -> None:
    g = section(text, "G")
    assert "denied as a sensitive file, because its grading directory sat under" not in g
    assert "a hypothesis until step 2 passes outside `.claude/`" in g
