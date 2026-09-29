"""Second-labeller sample, inter-rater agreement, and the disagreement list (docs/taxonomy.md §2.11, §4).

    uv run python -m tests.phase0.datasets.agreement sample <out dir>   # the seeded 20% sample (work lists)
    uv run python -m tests.phase0.datasets.agreement report             # kappas + disagreements -> labels/agreement.json
"""
from __future__ import annotations

import itertools
import json
import pathlib
import random
import sys

from tests.phase0 import rules as R
from tests.phase0.stats import cohen_kappa

HERE = pathlib.Path(__file__).resolve().parent
LABELS = HERE / "labels"
EXTRACTION = HERE / "extraction"
SHARE = 0.20


def sample_keys(keys: list, share: float = SHARE, seed: int = R.SEED) -> list:
    keys = sorted(keys)
    k = round(share * len(keys))
    return sorted(random.Random(seed).sample(keys, k))


def candidate_agreement(primary: dict[str, dict], second: dict[str, dict]) -> dict:
    """Kappa on option labels and on field status over every field instance both labellers labelled; kappa on the
    document-level multi_entity flag; and the list of instances on which they disagree."""
    opt_a, opt_b, st_a, st_b, me_a, me_b, dis = [], [], [], [], [], [], []
    for doc, sec in sorted(second.items()):
        pri = primary[doc]
        me_a.append(str(pri["multi_entity"]))
        me_b.append(str(sec["multi_entity"]))
        if pri["multi_entity"] != sec["multi_entity"]:
            dis.append({"kind": "doc", "doc_id": doc, "what": "multi_entity"})
        for fid, fs in sorted(sec["fields"].items()):
            fp = pri["fields"][fid]
            st_a.append(fp["status"])
            st_b.append(fs["status"])
            diff_opts = []
            for oid in sorted(fp["options"], key=lambda x: int(x[1:])):
                opt_a.append(fp["options"][oid])
                opt_b.append(fs["options"][oid])
                if fp["options"][oid] != fs["options"][oid]:
                    diff_opts.append(oid)
            if diff_opts or fp["status"] != fs["status"] or fp["superseded"] != fs["superseded"]:
                dis.append({"kind": "field", "doc_id": doc, "field_id": fid, "options": diff_opts,
                            "status": [fp["status"], fs["status"]], "superseded": [fp["superseded"], fs["superseded"]]})
    return {"n_documents": len(me_a), "n_field_instances": len(st_a), "n_option_labels": len(opt_a),
            "kappa_options": cohen_kappa(opt_a, opt_b) if opt_a else None,
            "agreement_options": sum(x == y for x, y in zip(opt_a, opt_b)) / len(opt_a) if opt_a else None,
            "kappa_status": cohen_kappa(st_a, st_b) if st_a else None,
            "agreement_status": sum(x == y for x, y in zip(st_a, st_b)) / len(st_a) if st_a else None,
            "kappa_multi_entity": cohen_kappa(me_a, me_b) if me_a else None,
            "disagreements": dis}


def _pairs(lab: dict) -> dict[tuple[str, str], str]:
    ms = {k: v for k, v in lab["mentions"].items() if not v["ambiguous"]}
    return {(a, b): "same" if ms[a]["entity"] == ms[b]["entity"] else "different"
            for a, b in itertools.combinations(sorted(ms, key=lambda x: int(x[1:])), 2)}


def mention_agreement(primary: dict[str, dict], second: dict[str, dict]) -> dict:
    """Kappa on same/different for every mention pair neither labeller marked ambiguous, and on the ambiguous and
    role-noun flags; disagreements are passages with any differing pair or flag."""
    pa, pb, amb_a, amb_b, rn_a, rn_b, dis = [], [], [], [], [], [], []
    for pid, sec in sorted(second.items()):
        pri = primary[pid]
        for mid in sorted(pri["mentions"], key=lambda x: int(x[1:])):
            amb_a.append(str(pri["mentions"][mid]["ambiguous"]))
            amb_b.append(str(sec["mentions"][mid]["ambiguous"]))
            rn_a.append(str(pri["mentions"][mid]["role_noun"]))
            rn_b.append(str(sec["mentions"][mid]["role_noun"]))
        a, b = _pairs(pri), _pairs(sec)
        common = sorted(set(a) & set(b))
        pa += [a[k] for k in common]
        pb += [b[k] for k in common]
        differ = [k for k in common if a[k] != b[k]]
        flags = [m for m in pri["mentions"] if pri["mentions"][m] != {**pri["mentions"][m], **{
            "ambiguous": sec["mentions"][m]["ambiguous"], "role_noun": sec["mentions"][m]["role_noun"]}}]
        if differ or flags:
            dis.append({"kind": "mentions", "passage_id": pid, "pairs": [list(k) for k in differ], "flags": flags})
    return {"n_passages": len(second), "n_pairs": len(pa),
            "kappa_pairs": cohen_kappa(pa, pb) if pa else None,
            "agreement_pairs": sum(x == y for x, y in zip(pa, pb)) / len(pa) if pa else None,
            "kappa_ambiguous": cohen_kappa(amb_a, amb_b) if amb_a else None,
            "kappa_role_noun": cohen_kappa(rn_a, rn_b) if rn_a else None,
            "disagreements": dis}


def _load_dir(d: pathlib.Path, key: str) -> dict[str, dict]:
    out = {}
    for p in sorted(d.glob("*.json")):
        x = json.loads(p.read_text())
        out[x[key]] = x
    return out


def main(argv: list[str], labels: pathlib.Path = LABELS, extraction: pathlib.Path = EXTRACTION) -> int:
    if argv[:1] == ["sample"] and len(argv) == 2:
        opts = [json.loads(x) for x in (extraction / "options.jsonl").read_text().splitlines()]
        inst = [(r["doc_id"], f["field_id"]) for r in opts for f in r["fields"] if not f["over_cap"]]
        chosen = sample_keys(inst)
        pids = sorted(_load_dir(labels / "mentions", "passage_id"))
        pchosen = sample_keys(pids)
        out = pathlib.Path(argv[1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "second_sample.json").write_text(json.dumps({"fields": chosen, "passages": pchosen}, indent=1))
        print(f"second sample: {len(chosen)} of {len(inst)} field instances, {len(pchosen)} of {len(pids)} passages")
        return 0
    if argv[:1] == ["report"]:
        rep = {"candidates": candidate_agreement(_load_dir(labels / "candidates", "doc_id"),
                                                 _load_dir(labels / "second" / "candidates", "doc_id")),
               "mentions": mention_agreement(_load_dir(labels / "mentions", "passage_id"),
                                             _load_dir(labels / "second" / "mentions", "passage_id"))}
        (labels / "agreement.json").write_text(json.dumps(rep, indent=1) + "\n")
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "disagreements"} | {
            "disagreements": len(v["disagreements"])} for k, v in rep.items()}, indent=1))
        return 0
    print("usage: agreement <sample <out dir>|report>", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
