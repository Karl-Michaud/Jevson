from __future__ import annotations

import pytest

from tests.phase0.datasets import extract as X


@pytest.mark.parametrize("vt,src,expected", [
    ("money", "Subtotal $1,204.50, tax 5.455, total Rp 60.000 and 82,000; fee 12.50", ["$1,204.50", "Rp 60.000", "5.455", "82,000", "12.50"]),
    ("date", "Signed September 7th, 1999; effective 1 January 2020; the 7th day of September, 1999; 03/04/2026; 2021-06-15; June 2003",
     ["September 7th, 1999", "1 January 2020", "7th day of September, 1999", "03/04/2026", "2021-06-15", "June 2003"]),
    ("date", "Publicado el 3 de enero de 2024 y el 15 de marzo", ["3 de enero de 2024", "15 de marzo"]),
    ("year", "B.A., 2002; J.D., 2005; 12002", ["2002", "2005"]),
    ("duration", "within thirty (30) days, a term of 2 years, sixty days", ["thirty (30) days", "2 years", "sixty days"]),
    ("email", "write to a.b+c@x-y.example.org now", ["a.b+c@x-y.example.org"]),
    ("phone", "call (520) 228-8343 or 415-522-3022 ext. 4", ["(520) 228-8343", "415-522-3022 ext. 4"]),
    ("url", "see https://example.com/a?b=1. or http://x.org)", ["https://example.com/a?b=1", "http://x.org"]),
    ("version", "Ubuntu 22.04 with kernel 6.5.0-14 and v2.1.3rc1", ["22.04", "6.5.0", "v2.1.3rc1"]),
    ("number", "54-year-old, 7.1 g/dL, 1,584.19 hours", ["54", "7.1", "1,584.19"]),
    ("text", "anything", []),
])
def test_patterns(vt, src, expected):
    got = X.pattern_candidates(src, vt)
    for e in expected:
        assert e in got, (e, got)


def test_unknown_type():
    with pytest.raises(ValueError):
        X.pattern_candidates("x", "colour")


def test_locate_boundaries_and_overlap():
    assert X.locate("in 2005 and 5 and 5x", "5") == [(12, 13)]
    assert X.locate("a---b", "--") == [(1, 3), (2, 4)]
    assert X.locate("aaa", "aa") == []
    assert X.locate("($5.00)", "$5.00") == [(1, 6)]
    assert X.locate("abc", "") == []
    assert X.locate("x-5-y", "5") == [(2, 3)]


def test_extract_union_rejects_and_orders():
    src = "Total 60.000\nCash 100.000\nChange 40.000\nTOTAL 60.000"
    ex = X.extract(src, "money", ["60.000", "  Change 40.000 ", "70.000", "", "Cash"])
    assert "70.000" in ex.rejected and "60.000" in ex.texts
    assert ex.options == sorted(ex.options)
    assert (6, 12) in ex.options and (46, 52) in ex.options
    assert ex.by_extractor["llm"] == ["60.000", "Change 40.000", "Cash"]
    assert "Change 40.000" in ex.texts
