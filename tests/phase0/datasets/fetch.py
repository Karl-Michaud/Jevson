"""Corpus acquisition for Phase 0 (docs/taxonomy.md §3).

Real, openly licensed documents only. Parsing and rendering are pure functions (tested); network access goes
through one injected ``httpx.Client`` so tests run it against a mock transport.

Rendering rules, fixed before any label or Jev call: HTML is rendered to text with block elements and <br> as
line breaks and entities decoded; a no-break space becomes a space; runs of spaces and tabs inside a line
collapse to one; lines are stripped; three or more line breaks collapse to two. Plain-text sources (CUAD) are
kept verbatim. The committed text is the document of record: offsets refer to it, and its SHA-256 is recorded.

    uv run python -m tests.phase0.datasets.fetch <domain> [<scratch dir>]
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import pathlib
import random
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser

import httpx

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
RETRIEVED = "2026-09-29"
UA = {"User-Agent": "Jevson-Phase0-research/1.0 (https://github.com/Project-Asterion/Jevson)"}
SEED = 20260929
PER_DOMAIN = 22
PER_DOMAIN_WIDE = 30        # receipts, CVs: widened before any labelling (docs/taxonomy.md §3)
PER_DOMAIN_CONTRACT = 50    # contracts: widened twice before any Jev call, for the hard-regime share (§3)

LICENCES = {
    "cc-by-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "cc-by-sa-4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
    "public-domain-us-gov": "https://www.usa.gov/government-copyright",
}


@dataclass
class Doc:
    doc_id: str
    domain: str
    language: str
    text: str
    source_url: str
    licence: str
    attribution: str
    notes: str = ""
    retrieved: str = RETRIEVED
    pool: str = "main"                     # "main" or "screen" (probe 6 benign pool only)
    meta: dict = field(default_factory=dict)

    def record(self) -> dict:
        d = asdict(self)
        d.pop("text")
        d["licence_url"] = LICENCES[self.licence]
        d["chars"] = len(self.text)
        d["sha256"] = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        d["path"] = f"{self.domain}/{self.doc_id}.txt"
        return d


# ---------------------------------------------------------------- rendering

_BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
          "table", "dt", "dd", "hr", "section", "title", "caption"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(fragment: str) -> str:
    p = _Text()
    p.feed(fragment)
    p.close()
    return tidy("".join(p.out))


# ---------------------------------------------------------------- per-source parsing (pure)

def cuad_docs(cuad: dict, k: int, seed: int = SEED, max_chars: int = 40000) -> list[Doc]:
    """k whole CUAD contracts of at most max_chars characters, sampled with the seed (titles sorted first)."""
    eligible = sorted((d["title"], d["paragraphs"][0]["context"]) for d in cuad["data"]
                      if len(d["paragraphs"][0]["context"]) <= max_chars)
    picked = random.Random(seed).sample(eligible, k)
    out, used = [], set()
    for title, ctx in sorted(picked):
        doc_id = "cuad-" + re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]
        if doc_id in used:   # two titles sharing their first 60 characters
            doc_id += "-" + hashlib.sha256(title.encode()).hexdigest()[:6]
        used.add(doc_id)
        out.append(Doc(doc_id, "contract", "en", ctx, "https://zenodo.org/records/4595826", "cc-by-4.0",
                       "The Atticus Project, CUAD v1 (CC BY 4.0)", notes=f"CUAD title: {title}"))
    return out


def cord_text(gt: dict) -> str:
    """Receipt text from CORD's annotated OCR words: words grouped into rows by row_id, rows in reading order
    (top y), words left to right."""
    rows: dict[int, list[tuple[int, int, str]]] = {}
    for line in gt["valid_line"]:
        for w in line["words"]:
            q = w["quad"]
            rows.setdefault(w["row_id"], []).append((min(q["y1"], q["y2"]), min(q["x1"], q["x4"]), w["text"]))
    ordered = sorted(rows.values(), key=lambda ws: (min(y for y, _, _ in ws), min(x for _, x, _ in ws)))
    return tidy("\n".join(" ".join(t for _, _, t in sorted(ws, key=lambda w: w[1])) for ws in ordered))


def cord_docs(ground_truths: list[str], k: int, seed: int = SEED, min_rows: int = 8) -> list[Doc]:
    texts = [(i, cord_text(json.loads(g))) for i, g in enumerate(ground_truths)]
    eligible = [(i, t) for i, t in texts if t.count("\n") + 1 >= min_rows]
    picked = sorted(random.Random(seed).sample(eligible, k))
    return [Doc(f"cord-test-{i:03d}", "receipt", "id", t,
                "https://huggingface.co/datasets/naver-clova-ix/cord-v2", "cc-by-4.0",
                "NAVER Clova, CORD v2 (CC BY 4.0)", notes=f"CORD v2 test split row {i}; text rebuilt from annotated OCR words")
            for i, t in picked]


def fjc_record_text(page: str) -> str | None:
    """The judge's name and biographical record from an FJC Biographical Directory page."""
    name = re.search(r"<h1>(.*?)</h1>", page, re.S)
    rec = re.search(r'field--name-judge-record-display.*?<div class="field__item even">(.*?)</div></div></div>', page, re.S)
    if not name or not rec:
        return None
    return tidy(html.unescape(re.sub(r"<[^>]+>", "", name.group(1))) + "\n\n" + html_to_text(rec.group(1)))


def fjc_candidates(judges_csv: str, k: int, seed: int = SEED) -> list[str]:
    """nids of judges born in 1940 or later with a professional career and at least two education entries,
    sampled with the seed."""
    rows = list(csv.DictReader(io.StringIO(judges_csv)))
    ok = sorted(r["nid"] for r in rows if (r.get("Professional Career") or "").strip()
                and (r.get("School (2)") or "").strip() and (r.get("Birth Year") or "").isdigit()
                and int(r["Birth Year"]) >= 1940)
    return random.Random(seed).sample(ok, min(k, len(ok)))


def se_text(item: dict) -> str:
    return tidy(html.unescape(item["title"]) + "\n\n" + html_to_text(item["body"]))


def se_docs(items: list[dict], site: str, language: str, k: int, seed: int = SEED,
            min_chars: int = 600, max_chars: int = 5000) -> list[Doc]:
    ok = []
    for it in sorted(items, key=lambda x: x["question_id"]):
        t = se_text(it)
        if min_chars <= len(t) <= max_chars and it.get("content_license") == "CC BY-SA 4.0":
            ok.append((it, t))
    picked = random.Random(seed).sample(ok, min(k, len(ok)))
    return [Doc(f"se-{site.split('.')[0]}-{it['question_id']}", "support_ticket", language, t, it["link"],
                "cc-by-sa-4.0", f"{html.unescape(it.get('owner', {}).get('display_name', 'unknown'))} on {site} (CC BY-SA 4.0)",
                notes=f"Stack Exchange question {it['question_id']} on {site}")
            for it, t in sorted(picked, key=lambda p: p[0]["question_id"])]


_CASE_TITLE = re.compile(r"case (presentation|report|description|history|summary|details)|presentation of case", re.I)


def epmc_case_text(xml_text: str) -> tuple[str, str] | None:
    """(article title, text of its case-presentation section(s)) if the article is CC BY and has one."""
    root = ET.fromstring(xml_text)
    bits = []
    for e in root.iter():
        tag = e.tag.rsplit("}", 1)[-1]
        if tag in ("license", "license_ref"):
            for sub in e.iter():
                bits.append(sub.get("{http://www.w3.org/1999/xlink}href", "") + " " + (sub.text or ""))
    lic = " ".join(bits)
    if not re.search(r"creativecommons\.org/licenses/by/", lic) or re.search(r"licenses/by-n|NonCommercial|NoDeriv", lic):
        return None
    title_el = root.find(".//article-title")
    title = tidy("".join(title_el.itertext())) if title_el is not None else ""
    parts = []
    for sec in root.iter("sec"):
        t = sec.find("title")
        if t is not None and _CASE_TITLE.search("".join(t.itertext())):
            paras = [tidy("".join(p.itertext())) for p in sec.iter("p")]
            parts.append("\n\n".join([tidy("".join(t.itertext()))] + [p for p in paras if p]))
    if not parts:
        return None
    return title, tidy("\n\n".join(parts))


def gsa_text(item: dict) -> str:
    return tidy(item["itemName"].strip() + "\n\n" + html_to_text(item.get("lotInfo") or ""))


FEDERAL = re.compile(r"^(Department of|U\.?S\.? |United States|Defense |General Services|National |Federal |Social Security"
                     r"|Environmental Protection|Small Business|Tennessee Valley|Smithsonian|Government )")


def gsa_docs(results: list[dict], k_main: int, k_screen: int, seed: int = SEED,
             min_chars: int = 400, max_chars: int = 10000) -> list[Doc]:
    ok = []
    for it in sorted(results, key=lambda x: str(x.get("itemDescURL"))):
        t = gsa_text(it)
        if FEDERAL.search(it.get("agencyName") or "") and min_chars <= len(t) <= max_chars:
            ok.append((it, t))
    rng = random.Random(seed)
    picked = rng.sample(ok, min(k_main + k_screen, len(ok)))
    out = []
    for n, (it, t) in enumerate(picked):
        sale = str(it["itemDescURL"]).rstrip("/").rsplit("/", 1)[-1]
        out.append(Doc(f"gsa-{sale}", "product_listing", "en", t, it["itemDescURL"], "public-domain-us-gov",
                       f"{it.get('agencyName')} via GSA Auctions (U.S. Government work)",
                       notes="GSA Auctions listing (itemName + lotInfo)", pool="main" if n < k_main else "screen"))
    return out


# ---------------------------------------------------------------- writing

def write_docs(docs: list[Doc], root: pathlib.Path = CORPUS) -> None:
    """Write the documents and replace every earlier record (and file) of the same domains in the manifest."""
    manifest = root / "manifest.jsonl"
    domains = {d.domain for d in docs}
    existing = {}
    if manifest.exists():
        for line in manifest.read_text().splitlines():
            r = json.loads(line)
            if r["domain"] in domains:
                (root / r["path"]).unlink(missing_ok=True)
            else:
                existing[r["doc_id"]] = r
    for d in docs:
        p = root / d.domain / f"{d.doc_id}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(d.text, encoding="utf-8")
        existing[d.doc_id] = d.record()
    manifest.write_text("".join(json.dumps(existing[k], ensure_ascii=False) + "\n" for k in sorted(existing)))


# ---------------------------------------------------------------- network (thin)

def fetch_fjc(client: httpx.Client, k: int) -> list[Doc]:
    csv_text = client.get("https://www.fjc.gov/sites/default/files/history/judges.csv").text
    out = []
    for nid in fjc_candidates(csv_text, k * 2):
        url = f"https://www.fjc.gov/node/{nid}"
        r = client.get(url)
        text = fjc_record_text(r.text) if r.status_code == 200 else None
        if text:
            out.append(Doc(f"fjc-{nid}", "resume", "en", text, str(r.url), "public-domain-us-gov",
                           "Federal Judicial Center, Biographical Directory of Article III Federal Judges",
                           notes="FJC judge record (name + biographical record block)"))
        if len(out) == k:
            break
    return out


def fetch_se(client: httpx.Client, site: str, language: str, k: int, fromdate: int, todate: int) -> list[Doc]:
    r = client.get("https://api.stackexchange.com/2.3/questions",
                   params={"site": site, "sort": "creation", "order": "asc", "fromdate": fromdate,
                           "todate": todate, "filter": "withbody", "pagesize": 100})
    return se_docs(r.json()["items"], site, language, k)


def fetch_epmc(client: httpx.Client, k: int, query: str) -> list[Doc]:
    r = client.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                   params={"query": query, "format": "json", "pageSize": 100, "resultType": "lite"})
    ids = sorted(x["pmcid"] for x in r.json()["resultList"]["result"] if x.get("pmcid"))
    out = []
    for pmcid in random.Random(SEED).sample(ids, len(ids)):
        x = client.get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML")
        got = epmc_case_text(x.text) if x.status_code == 200 else None
        if got and 1500 <= len(got[1]) <= 12000:
            title, text = got
            out.append(Doc(f"epmc-{pmcid.lower()}", "medical_intake", "en", text,
                           f"https://europepmc.org/article/PMC/{pmcid}", "cc-by-4.0",
                           f"Authors of \"{title}\" ({pmcid}), CC BY", notes="case-presentation section(s) only"))
        if len(out) == k:
            break
    return out


def fetch_gsa(client: httpx.Client, k_main: int, k_screen: int) -> list[Doc]:
    r = client.get("https://api.gsa.gov/assets/gsaauctions/v2/auctions", params={"api_key": "DEMO_KEY", "format": "JSON"})
    return gsa_docs(r.json()["Results"], k_main, k_screen)


def main(argv: list[str], client: httpx.Client | None = None, root: pathlib.Path = CORPUS) -> int:
    if not argv:
        print("usage: fetch <cuad|cord|fjc|se|epmc|gsa> [scratch dir]", file=sys.stderr)
        return 2
    src, scratch = argv[0], pathlib.Path(argv[1]) if len(argv) > 1 else pathlib.Path(".")
    client = client or httpx.Client(headers=UA, follow_redirects=True, timeout=60)
    if src == "cuad":   # CUADv1.json from https://github.com/TheAtticusProject/cuad/raw/main/data.zip
        docs = cuad_docs(json.loads((scratch / "CUADv1.json").read_text()), PER_DOMAIN_CONTRACT)
    elif src == "cord":  # ground_truth column of the CORD v2 test parquet, one JSON string per line
        docs = cord_docs((scratch / "cord_test_ground_truth.jsonl").read_text().splitlines(), PER_DOMAIN_WIDE)
    elif src == "fjc":
        docs = fetch_fjc(client, PER_DOMAIN_WIDE)
    elif src == "se":
        docs = (fetch_se(client, "superuser", "en", 6, 1704067200, 1704153600)
                + fetch_se(client, "askubuntu", "en", 6, 1704067200, 1704153600)
                + fetch_se(client, "es.stackoverflow", "es", 10, 1704067200, 1704672000))
    elif src == "epmc":
        docs = fetch_epmc(client, PER_DOMAIN, 'PUB_TYPE:"Case Reports" AND LICENSE:"cc by" AND OPEN_ACCESS:y '
                                              'AND LANG:eng AND FIRST_PDATE:[2024-01-01 TO 2024-01-31]')
    elif src == "gsa":
        docs = fetch_gsa(client, PER_DOMAIN, 40)
    else:
        print(f"unknown source {src}", file=sys.stderr)
        return 2
    write_docs(docs, root)
    print(f"{src}: wrote {len(docs)} documents")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
