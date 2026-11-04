"""Builds the Phase 0 data products from the recorded extractor output and the labels.

    uv run python -m tests.phase0.datasets.build options      # extraction -> options.jsonl + labelling work lists
    uv run python -m tests.phase0.datasets.build mentions     # mention extraction -> mentions.jsonl
    uv run python -m tests.phase0.datasets.build cases        # labels -> case files (probes 1-4, 6, 8)

Every step is deterministic given its inputs; the case files are reproducible from the committed labels.
"""
from __future__ import annotations

import json
import pathlib
import sys

from tests.phase0.datasets import extract as X
from tests.phase0.datasets import fields as FL
from tests.phase0.datasets.models import CORPUS, doc_text, load_manifest, premerge_key
from tests.phase0.templates import context_window

HERE = pathlib.Path(__file__).resolve().parent
EXTRACTION = HERE / "extraction"
LABELS = HERE / "labels"
CASES = HERE / "cases"


def options_for_doc(text: str, llm_fields: dict[str, list[str]], domain: str) -> list[dict]:
    out = []
    for f in FL.for_domain(domain):
        ex = X.extract(text, f.value_type, llm_fields.get(f.field_id, []))
        opts = [{"id": f"c{i}", "text": text[s:e], "start": s, "end": e,
                 "context": context_window(text, s, e, 60)} for i, (s, e) in enumerate(ex.options)]
        out.append({"field_id": f.field_id, "label": f.label, "guidance": f.guidance, "value_type": f.value_type,
                    "n_options": len(opts), "over_cap": len(opts) > 50, "options": opts,
                    "texts": ex.texts, "by_extractor": ex.by_extractor, "rejected": ex.rejected})
    return out


def build_options(root: pathlib.Path = CORPUS, extraction: pathlib.Path = EXTRACTION, pool: str = "main") -> list[dict]:
    recs = []
    for d in sorted(load_manifest(root).values(), key=lambda r: r.doc_id):
        if d.pool != pool:
            continue
        llm = json.loads((extraction / "llm" / f"{d.doc_id}.json").read_text())
        if llm["doc_id"] != d.doc_id:
            raise ValueError(f"extraction file for {d.doc_id} names {llm['doc_id']}")
        recs.append({"doc_id": d.doc_id, "domain": d.domain, "language": d.language,
                     "path": f"tests/phase0/datasets/corpus/{d.path}", "chars": d.chars,
                     "fields": options_for_doc(doc_text(d, root), llm["fields"], d.domain)})
    return recs


def premerge(passage_text: str, offset: int, strings: list[str]) -> tuple[list[dict], list[str]]:
    """Locate each mention string in the passage (exact match, word boundaries), merge strings whose DESIGN §5.7
    normalised forms are identical, and return (mentions in order of first occurrence, rejected strings)."""
    groups: dict[str, dict] = {}
    rejected = []
    for s in dict.fromkeys(x.strip() for x in strings):
        if not s:
            continue
        spans = [(offset + a, offset + b) for a, b in X.locate(passage_text, s)]
        if not spans:
            rejected.append(s)
            continue
        g = groups.setdefault(premerge_key(s), {"texts": [], "spans": []})
        g["texts"].append(s)
        g["spans"].extend(spans)
    ordered = sorted(groups.values(), key=lambda g: min(g["spans"]))
    mentions = []
    for i, g in enumerate(ordered):
        first = min(g["spans"])
        mentions.append({"id": f"c{i}", "text": next(t for t in g["texts"] if first[1] - first[0] == len(t)
                                                      and passage_text[first[0] - offset:first[1] - offset] == t),
                         "spans": sorted(set(g["spans"])), "merged_texts": g["texts"]})
    return mentions, rejected


def build_mentions(root: pathlib.Path = CORPUS, extraction: pathlib.Path = EXTRACTION) -> list[dict]:
    docs = load_manifest(root)
    out = []
    for p in sorted((extraction / "mentions").glob("*.json")):
        m = json.loads(p.read_text())
        text = doc_text(docs[m["doc_id"]], root)
        passage = text[m["start"]:m["end"]]
        mentions, rejected = premerge(passage, m["start"], m["mentions"])
        out.append({"passage_id": m["passage_id"], "doc_id": m["doc_id"], "domain": docs[m["doc_id"]].domain,
                    "entity_type": m["entity_type"], "start": m["start"], "end": m["end"],
                    "path": f"tests/phase0/datasets/corpus/{docs[m['doc_id']].path}",
                    "n_mentions": len(mentions), "mentions": mentions, "rejected": rejected})
    return out


def write_jsonl(recs: list[dict], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))


def main(argv: list[str], root: pathlib.Path = CORPUS, extraction: pathlib.Path = EXTRACTION) -> int:
    if argv[:1] == ["options"]:
        pool = argv[1] if len(argv) > 1 else "main"
        recs = build_options(root, extraction, pool)
        write_jsonl(recs, extraction / ("options.jsonl" if pool == "main" else f"options_{pool}.jsonl"))
        n = sum(len(r["fields"]) for r in recs)
        print(f"options: {len(recs)} documents, {n} field instances, "
              f"{sum(f['over_cap'] for r in recs for f in r['fields'])} over the 50-option cap")
        return 0
    if argv[:1] == ["mentions"]:
        recs = build_mentions(root, extraction)
        write_jsonl(recs, extraction / "mentions.jsonl")
        print(f"mentions: {len(recs)} passages")
        return 0
    print("usage: build <options|mentions>", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
