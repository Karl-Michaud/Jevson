from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from tests.phase0.datasets import fetch as F


def test_html_to_text_and_tidy():
    h = "<p>Hello&nbsp;<b>world</b></p><ul><li>a</li><li>b &amp; c</li></ul><script>x()</script><br>end"
    assert F.html_to_text(h) == "Hello world\n\na\n\nb & c\n\nend"
    assert F.tidy("a\r\n\r\n\r\n\r\nb  \t c\rd") == "a\n\nb c\nd"


def _cuad(n):
    return {"data": [{"title": f"T{i}", "paragraphs": [{"context": "x" * (10 + i)}]} for i in range(n)]
            + [{"title": "LONG", "paragraphs": [{"context": "y" * 50001}]}]}


def test_cuad_docs_sample_and_record():
    docs = F.cuad_docs(_cuad(10), 3, max_chars=40000)
    assert len(docs) == 3 and all(d.domain == "contract" and d.licence == "cc-by-4.0" for d in docs)
    assert all("LONG" not in d.notes for d in docs)
    r = docs[0].record()
    assert r["sha256"] == hashlib.sha256(docs[0].text.encode()).hexdigest() and "text" not in r
    assert r["licence_url"].startswith("https://creativecommons.org/licenses/by/4.0")
    assert F.cuad_docs(_cuad(10), 3) == F.cuad_docs(_cuad(10), 3)


def test_cuad_ids_unique_when_titles_share_a_prefix():
    long = "X" * 70
    cuad = {"data": [{"title": long + "A", "paragraphs": [{"context": "a"}]},
                     {"title": long + "B", "paragraphs": [{"context": "b"}]}]}
    ids = [d.doc_id for d in F.cuad_docs(cuad, 2)]
    assert len(set(ids)) == 2 and ids[0] == "cuad-" + "x" * 60


def _word(text, row, x, y):
    return {"text": text, "row_id": row, "quad": {"x1": x, "x4": x, "y1": y, "y2": y}}


def test_cord_text_orders_rows_and_words():
    gt = {"valid_line": [{"words": [_word("100", 2, 50, 20), _word("TOTAL", 2, 5, 21)]},
                         {"words": [_word("ITEM", 1, 5, 10), _word("A", 1, 30, 10)]}]}
    assert F.cord_text(gt) == "ITEM A\nTOTAL 100"


def test_cord_docs_filters_short():
    long_gt = {"valid_line": [{"words": [_word(f"L{i}", i, 0, i)]} for i in range(9)]}
    short_gt = {"valid_line": [{"words": [_word("x", 0, 0, 0)]}]}
    docs = F.cord_docs([json.dumps(short_gt), json.dumps(long_gt)], 1)
    assert [d.doc_id for d in docs] == ["cord-test-001"] and docs[0].language == "id"


def test_fjc_record_text():
    page = ('<h1>Doe, Jane</h1><div class="field--name-judge-record-display x"><div class="field__items">'
            '<div class="field__item even">Born 1960 in Reno, NV<br><br><b>Education:</b><br> Yale, B.A., 1982'
            '</div></div></div>')
    assert F.fjc_record_text(page) == "Doe, Jane\n\nBorn 1960 in Reno, NV\n\nEducation:\nYale, B.A., 1982"
    assert F.fjc_record_text("<html></html>") is None


def test_fjc_candidates():
    csv_text = ('"nid","Birth Year","School (2)","Professional Career"\n'
                '"1","1950","Yale","Lawyer"\n"2","","Yale","Lawyer"\n"3","1930","Yale","Lawyer"\n'
                '"4","1960","","Lawyer"\n"5","1970","Harvard","Clerk"\n')
    assert sorted(F.fjc_candidates(csv_text, 2)) == ["1", "5"]


def _se_item(qid, body, lic="CC BY-SA 4.0"):
    return {"question_id": qid, "title": "Q &amp; A", "body": body, "link": f"https://x/{qid}",
            "content_license": lic, "owner": {"display_name": "Jos&#233;"}}


def test_se_docs_filters_length_and_licence():
    items = [_se_item(1, "<p>" + "a" * 700 + "</p>"), _se_item(2, "<p>short</p>"),
             _se_item(3, "<p>" + "b" * 700 + "</p>", lic="CC BY-SA 3.0")]
    docs = F.se_docs(items, "superuser", "en", 5)
    assert [d.doc_id for d in docs] == ["se-superuser-1"] and docs[0].text.startswith("Q & A\n\n")
    assert docs[0].attribution.startswith("José on superuser")


EPMC_OK = """<article xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:ali="http://www.niso.org/schemas/ali/1.0/">
<front><article-meta><title-group><article-title>A case</article-title></title-group>
<permissions><license><ali:license_ref>https://creativecommons.org/licenses/by/4.0/</ali:license_ref>
<license-p>Open access.</license-p></license></permissions></article-meta></front>
<body><sec><title>Introduction</title><p>intro</p></sec>
<sec><title>Case presentation</title><p>A 54-year-old woman.</p><p>She recovered.</p></sec></body></article>"""


def test_epmc_case_text():
    title, text = F.epmc_case_text(EPMC_OK)
    assert title == "A case" and text == "Case presentation\n\nA 54-year-old woman.\n\nShe recovered."
    nc = EPMC_OK.replace("licenses/by/4.0", "licenses/by-nc/4.0")
    assert F.epmc_case_text(nc) is None
    no_sec = EPMC_OK.replace("Case presentation", "Methods")
    assert F.epmc_case_text(no_sec) is None
    href = EPMC_OK.replace("<ali:license_ref>https://creativecommons.org/licenses/by/4.0/</ali:license_ref>",
                           '<license-p><ext-link xlink:href="https://creativecommons.org/licenses/by/4.0/">CC BY</ext-link></license-p>')
    assert F.epmc_case_text(href) is not None
    notitle = EPMC_OK.replace("<article-title>A case</article-title>", "")
    assert F.epmc_case_text(notitle)[0] == ""


def _gsa(url, agency, n=500):
    return {"itemDescURL": url, "agencyName": agency, "itemName": "Truck ", "lotInfo": "<p>" + "z" * n + "</p>"}


def test_gsa_docs_federal_only_and_pools():
    res = [_gsa(f"https://g/preview/{i}", "Department of the Navy") for i in range(5)]
    res += [_gsa("https://g/preview/99", "State of Ohio"), _gsa("https://g/preview/98", "Department of X", 10)]
    docs = F.gsa_docs(res, 2, 2)
    assert len(docs) == 4 and [d.pool for d in docs] == ["main", "main", "screen", "screen"]
    assert all(d.doc_id != "gsa-99" and d.doc_id != "gsa-98" for d in docs)
    assert docs[0].text.startswith("Truck\n\n")


def test_write_docs_replaces_domain(tmp_path):
    a = F.Doc("a", "contract", "en", "text a", "u", "cc-by-4.0", "x")
    b = F.Doc("b", "receipt", "id", "text b", "u", "cc-by-4.0", "x")
    F.write_docs([a, b], tmp_path)
    c = F.Doc("c", "contract", "en", "text c", "u", "cc-by-4.0", "x")
    F.write_docs([c], tmp_path)
    ids = [json.loads(l)["doc_id"] for l in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert ids == ["b", "c"] and not (tmp_path / "contract" / "a.txt").exists()
    assert (tmp_path / "contract" / "c.txt").read_text() == "text c"


# ---------------------------------------------------------------- network functions via a mock transport

def _router(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if u.endswith("judges.csv"):
        return httpx.Response(200, text='"nid","Birth Year","School (2)","Professional Career"\n"7","1970","Yale","Clerk"\n"8","1971","Yale","Clerk"\n')
    if "/node/7" in u:
        return httpx.Response(200, text=('<h1>Roe, Ann</h1><div class="field--name-judge-record-display"><div class="field__items">'
                                         '<div class="field__item even">Born 1970</div></div></div>'))
    if "/node/8" in u:
        return httpx.Response(404, text="")
    if "api.stackexchange.com" in u:
        return httpx.Response(200, json={"items": [_se_item(5, "<p>" + "q" * 800 + "</p>")]})
    if "europepmc" in u and "search" in u:
        return httpx.Response(200, json={"resultList": {"result": [{"pmcid": "PMC1"}, {"pmcid": "PMC2"}, {"x": 1}]}})
    if "PMC1/fullTextXML" in u:
        return httpx.Response(200, text=EPMC_OK.replace("A 54-year-old woman.", "A 54-year-old woman. " + "w" * 1600))
    if "PMC2/fullTextXML" in u:
        return httpx.Response(404, text="")
    if "api.gsa.gov" in u:
        return httpx.Response(200, json={"Results": [_gsa(f"https://g/preview/{i}", "Department of Energy") for i in range(3)]})
    return httpx.Response(500)


@pytest.fixture
def client():
    return httpx.Client(transport=httpx.MockTransport(_router))


def test_fetchers_with_mock_transport(client):
    assert [d.doc_id for d in F.fetch_fjc(client, 1)] == ["fjc-7"]
    assert len(F.fetch_fjc(client, 5)) == 1
    assert [d.doc_id for d in F.fetch_se(client, "askubuntu", "en", 3, 0, 1)] == ["se-askubuntu-5"]
    assert [d.doc_id for d in F.fetch_epmc(client, 1, "q")] == ["epmc-pmc1"]
    assert len(F.fetch_gsa(client, 1, 1)) == 2


def test_main_dispatch(tmp_path, client, monkeypatch, capsys):
    scratch = tmp_path / "s"
    scratch.mkdir()
    (scratch / "CUADv1.json").write_text(json.dumps(_cuad(60)))
    long_gt = {"valid_line": [{"words": [_word(f"L{i}", i, 0, i)]} for i in range(9)]}
    (scratch / "cord_test_ground_truth.jsonl").write_text("\n".join(json.dumps(long_gt) for _ in range(30)))
    root = tmp_path / "corpus"
    for src in ("cuad", "cord", "fjc", "se", "epmc", "gsa"):
        assert F.main([src, str(scratch)], client=client, root=root) == 0
    assert F.main([], client=client, root=root) == 2
    assert F.main(["nope"], client=client, root=root) == 2
    out = capsys.readouterr().out
    assert "cuad: wrote 50 documents" in out
    monkeypatch.setattr(F.httpx, "Client", lambda **kw: client)
    assert F.main(["gsa"], root=root) == 0
