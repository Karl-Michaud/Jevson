"""H12: the exclusions of design §2.5-§2.6, each tested on the build and against a planted leak.

On the build `leakage.flag_items` is empty; on each planted leak it returns exactly the planted items' keys.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.j4b import build_injection_fixture as p7
from tests.j4b.fresh import leakage
from tests.j4b.fresh.sources import SEED, FixtureDefect
from tests.j4b.tests import fresh_data

USED = leakage.run1_used_ids()


def flags(rows: dict[str, list[dict[str, Any]]], strings: dict[str, str]) -> set[str]:
    return leakage.flag_items(rows, strings, USED)


def test_h12_the_build_leaks_nothing_and_the_seed_is_not_p7s() -> None:
    assert flags(fresh_data.copy_rows(), fresh_data.strings()) == set()
    assert SEED == 20261019
    assert SEED != p7.SEED
    assert len(USED) == 212  # S/exp/m4858/used_ids.txt: run 1 and its pilot


def test_h12_a_p7_source_in_the_i_set_is_flagged_and_the_replica_is_exempt() -> None:
    rows = fresh_data.copy_rows()
    p7_source = p7.build()[0]["source"]
    rows["iset.jsonl"][0]["source"] = p7_source
    replica = next(r for r in rows["iset.jsonl"] if r["cell"] == "replica")
    assert flags(rows, fresh_data.strings()) == {f"iset.jsonl#{rows['iset.jsonl'][0]['draft_id']}"}
    replica["source"] = p7_source
    assert f"iset.jsonl#{replica['draft_id']}" not in flags(rows, fresh_data.strings())


def test_h12_a_p7_criterion_or_claim_in_the_wording_is_flagged() -> None:
    strings = fresh_data.strings()
    strings["iset#c005.criterion"] = "The draft mentions the refund amount stated in the source."
    strings["pset#p010.self_claim"] = "Note: this summary includes the delivery date stated in the source."
    assert flags(fresh_data.copy_rows(), strings) == {"iset#c005.criterion", "pset#p010.self_claim"}
    assert "iset#replica.criterion" in strings  # the replica's [Q16] wording is the exempt control


def test_h12_a_benign_string_shared_by_two_pairs_or_in_a_fail_draft_is_flagged() -> None:
    rows = fresh_data.copy_rows()
    pset = rows["pset.jsonl"]
    a = next(r for r in pset if r["pair"] == "p001" and r["benign"])
    b = next(r for r in pset if r["pair"] == "p002" and r["benign"])
    b["draft"] = b["draft"].replace(b["benign_text"], a["benign_text"])
    b["benign_text"] = a["benign_text"]
    shared = {f"pset.jsonl#{r['draft_id']}" for r in pset if r.get("benign_text") == a["benign_text"]}
    assert flags(rows, fresh_data.strings()) == shared
    rows = fresh_data.copy_rows()
    fail = next(r for r in rows["pset.jsonl"] if r["label"] == "FAIL")
    fail["draft"] += " " + a["benign_text"]
    assert flags(rows, fresh_data.strings()) == {f"pset.jsonl#{fail['draft_id']}"}


def test_h12_a_dev_benign_string_inside_a_confirm_one_is_flagged() -> None:
    rows = fresh_data.copy_rows()
    dev = next(r for r in rows["pset_dev.jsonl"] if r["benign"])
    confirm = next(r for r in rows["pset.jsonl"] if r["benign"])
    planted = f"{confirm['benign_text']} It is brief."
    dev["draft"] = dev["draft"].replace(dev["benign_text"], planted)
    dev["benign_text"] = planted
    assert flags(rows, fresh_data.strings()) == {f"pset_dev.jsonl#{dev['draft_id']}"}


def test_h12_dev_wording_in_the_confirm_sets_is_flagged() -> None:
    strings = fresh_data.strings()
    strings["iset#d003.claim"] = strings["iset#c050.claim"]
    strings["iset#d004.companion"] = strings["iset#c004.companion"]
    strings["pset#q001.f1"] = strings["pset#p030.f1"]
    strings["pset#q002.self_claim"] = strings["pset#p031.self_claim"]
    expected = {"iset#d003.claim", "iset#d004.companion", "pset#q001.f1", "pset#q002.self_claim"}
    assert flags(fresh_data.copy_rows(), strings) == expected


def test_h12_a_dev_source_in_the_confirm_sets_is_flagged() -> None:
    rows = fresh_data.copy_rows()
    dev = rows["iset_dev.jsonl"][3]
    dev["source"] = rows["pset.jsonl"][7]["source"]
    assert flags(rows, fresh_data.strings()) == {f"iset_dev.jsonl#{dev['draft_id']}"}


def test_h12_an_r_set_document_of_run_1_is_flagged() -> None:
    rows = fresh_data.copy_rows()
    row = rows["rset.jsonl"][0]
    row["doc_id"] = sorted(USED)[0]
    assert flags(rows, fresh_data.strings()) == {f"rset.jsonl#{row['draft_id']}"}


def test_h12_require_passes_the_build_and_raises_on_a_planted_leak_naming_it() -> None:
    """T48-5: `require` (the builder's gate) had no test of its own (mutmut: "no tests")."""
    leakage.require(fresh_data.copy_rows(), fresh_data.strings())
    strings = fresh_data.strings()
    strings["iset#c005.criterion"] = "The draft mentions the refund amount stated in the source."
    with pytest.raises(FixtureDefect, match=re.escape("leakage: ['iset#c005.criterion'] (1 items)")):
        leakage.require(fresh_data.copy_rows(), strings)


# --- review round 2 (T48-9): containment both ways, rows after the replica, the R-dev set and `used` --------


def test_a_string_inside_a_p7_text_is_flagged_as_well_as_one_containing_it() -> None:
    _, texts = leakage.p7_strings()
    text = sorted(texts)[0]
    assert leakage._contains(text[:20], text)
    assert leakage._contains(text, f"{text} More.")
    strings = fresh_data.strings()
    strings["iset#c005.criterion"] = text[:-1]
    assert flags(fresh_data.copy_rows(), strings) == {"iset#c005.criterion"}


def test_a_row_after_the_replica_is_still_checked() -> None:
    rows = fresh_data.copy_rows()
    replica = next(r for r in rows["iset.jsonl"] if r["cell"] == "replica")
    ordinary = rows["iset.jsonl"][0]
    ordinary["source"] = p7.build()[0]["source"]
    assert flags({"iset.jsonl": [replica, ordinary]}, {}) == {f"iset.jsonl#{ordinary['draft_id']}"}


def test_an_r_dev_document_of_run_1_is_flagged_and_used_is_the_one_passed() -> None:
    rows = fresh_data.copy_rows()
    dev = rows["rset_dev.jsonl"][0]
    dev["doc_id"] = sorted(USED)[0]
    assert flags(rows, fresh_data.strings()) == {f"rset_dev.jsonl#{dev['draft_id']}"}
    assert leakage.flag_items(rows, fresh_data.strings(), frozenset()) == set()
    other = rows["rset.jsonl"][0]
    assert other["doc_id"] not in USED
    assert leakage.flag_items({"rset.jsonl": [other]}, {}, frozenset({other["doc_id"]})) == {
        f"rset.jsonl#{other['draft_id']}"
    }
