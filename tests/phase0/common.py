"""Loading shared by the thin runners: documents and the committed case files. Paths are read at call time so tests
can point the runners at a fixture corpus."""
from __future__ import annotations

import json
import pathlib

from tests.phase0.datasets import models as M

HERE = pathlib.Path(__file__).resolve().parent
CASES = HERE / "datasets" / "cases"
CORPUS = M.CORPUS
RESULTS = HERE / "results"


def _paths(cases: pathlib.Path | None, root: pathlib.Path | None) -> tuple[pathlib.Path, pathlib.Path]:
    return cases or CASES, root or CORPUS


def texts(root: pathlib.Path | None = None) -> dict[str, str]:
    root = root or CORPUS
    return {d: M.doc_text(r, root) for d, r in M.load_manifest(root).items()}


def domains(root: pathlib.Path | None = None) -> dict[str, str]:
    return {d: r.domain for d, r in M.load_manifest(root or CORPUS).items()}


def selection(cases: pathlib.Path | None = None, root: pathlib.Path | None = None):
    cases, root = _paths(cases, root)
    return M.load_selection(cases / "probe1_3.jsonl", root), M.load_selection(cases / "probe2.jsonl", root)


def clusters(cases: pathlib.Path | None = None, root: pathlib.Path | None = None):
    cases, root = _paths(cases, root)
    return M.load_clusters(cases / "probe4.jsonl", root)


def hostile(cases: pathlib.Path | None = None, root: pathlib.Path | None = None):
    cases, root = _paths(cases, root)
    present, _ = selection(cases, root)
    base = {c.case_id: c for c in present}
    return (M.load_hostile(cases / "probe6_attacked.jsonl", base, root),
            M.load_screen(cases / "probe6_benign.jsonl", root), base)


def single(cases: pathlib.Path | None = None, root: pathlib.Path | None = None):
    cases, root = _paths(cases, root)
    return M.load_single(cases / "probe8.jsonl", root)


def read_result(name: str, results: pathlib.Path | None = None) -> dict:
    return json.loads(((results or RESULTS) / f"{name}.json").read_text())
