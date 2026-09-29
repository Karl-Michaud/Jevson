"""Case-file models and validators for the Phase 0 datasets (docs/taxonomy.md §2.2, §2.4, §2.6, §2.8, §3).

Every case file is JSONL, one case per line. ``load_*`` validates each case against the document it cites:
offsets must reproduce the option text exactly, ids must be unique, labels must be present, present-answer cases
must offer a correct span and absent-answer cases must not.
"""
from __future__ import annotations

import json
import pathlib
import re
import unicodedata
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from tests.phase0 import rules as R

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
_OPT_ID = re.compile(r"^c(0|[1-9]\d*)$")

Label = Literal["correct", "partial", "wrong"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DocRecord(Strict):
    doc_id: str
    domain: Literal["contract", "receipt", "resume", "support_ticket", "medical_intake", "product_listing"]
    language: str
    source_url: str
    licence: Literal["cc-by-4.0", "cc-by-sa-4.0", "public-domain-us-gov"]
    licence_url: str
    attribution: str
    notes: str = ""
    retrieved: str
    pool: Literal["main", "screen"] = "main"
    meta: dict = Field(default_factory=dict)
    chars: int
    sha256: str
    path: str


class Span(Strict):
    text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("span end must be after start")
        if self.end - self.start != len(self.text):
            raise ValueError("span length differs from its text")
        return self


class Option(Span):
    id: str
    label: Label

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _OPT_ID.match(v):
            raise ValueError("option ids are opaque c0..cN")
        return v


def _check_spans_against(text: str, spans: Iterable[Span], what: str) -> None:
    for s in spans:
        if s.end > len(text) or text[s.start:s.end] != s.text:
            raise ValueError(f"{what}: offsets [{s.start},{s.end}) do not reproduce {s.text!r}")
        if unicodedata.combining(text[s.start]) or (s.end < len(text) and unicodedata.combining(text[s.end])):
            raise ValueError(f"{what}: span boundary splits a combining sequence")


def _check_options(options: list[Option], where: str) -> None:
    ids = [o.id for o in options]
    if ids != [f"c{i}" for i in range(len(options))]:
        raise ValueError(f"{where}: option ids must be c0..cN in order")
    keys = [(o.start, o.end) for o in options]
    if keys != sorted(keys):
        raise ValueError(f"{where}: options must be in source order")
    if len(set(keys)) != len(keys):
        raise ValueError(f"{where}: duplicate option span")


class SelectionCase(Strict):
    """A probe 1/3 (present-answer) or probe 2 (absent-answer) case."""

    case_id: str
    probe: Literal["p1p3", "p2"]
    doc_id: str
    field_id: str
    label: str = Field(min_length=3)
    options: list[Option]
    removed: list[Option] = Field(default_factory=list)
    hard: bool
    repeated: bool
    superseded: bool
    multi_entity: bool

    @model_validator(mode="after")
    def _shape(self):
        _check_options(self.options, self.case_id)
        n_correct = sum(o.label == "correct" for o in self.options)
        others = len(self.options) - n_correct
        if len(self.options) > R.MAX_OPTIONS:
            raise ValueError(f"{self.case_id}: more than {R.MAX_OPTIONS} options")
        if self.probe == "p1p3":
            if n_correct < 1:
                raise ValueError(f"{self.case_id}: present-answer case without a correct option")
            if others < R.MIN_COMPETITORS:
                raise ValueError(f"{self.case_id}: fewer than {R.MIN_COMPETITORS} competitors")
            if self.removed:
                raise ValueError(f"{self.case_id}: present-answer case with removed options")
        else:
            if n_correct:
                raise ValueError(f"{self.case_id}: absent-answer case still offers a correct option")
            if len(self.options) < R.MIN_COMPETITORS:
                raise ValueError(f"{self.case_id}: fewer than {R.MIN_COMPETITORS} remaining options")
            gone = {o.text for o in self.removed if o.label == "correct"}
            if not gone:
                raise ValueError(f"{self.case_id}: absent-answer case removed no correct option")
            if any(o.label != "correct" and o.text not in gone for o in self.removed):
                raise ValueError(f"{self.case_id}: removed an option that is neither correct nor same-text")
            if any(o.text in gone for o in self.options):
                raise ValueError(f"{self.case_id}: the correct text is still offered")
        return self


class Mention(Strict):
    id: str
    text: str = Field(min_length=1)
    spans: list[tuple[int, int]] = Field(min_length=1)
    gold: str = Field(min_length=1)
    role_noun: bool


class Cluster(Strict):
    """A probe 4 cluster: a passage of a real document and its pre-merged mentions with gold entities."""

    cluster_id: str
    doc_id: str
    entity_type: Literal["person", "organization"]
    passage_start: int = Field(ge=0)
    passage_end: int
    mentions: list[Mention]
    excluded: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _shape(self):
        if self.passage_end <= self.passage_start:
            raise ValueError(f"{self.cluster_id}: empty passage")
        n = len(self.mentions)
        if not R.MIN_MENTIONS <= n <= R.MAX_MENTIONS:
            raise ValueError(f"{self.cluster_id}: {n} mentions outside [{R.MIN_MENTIONS}, {R.MAX_MENTIONS}]")
        if [m.id for m in self.mentions] != [f"c{i}" for i in range(n)]:
            raise ValueError(f"{self.cluster_id}: mention ids must be c0..cN in order")
        norm = [premerge_key(m.text) for m in self.mentions]
        if len(set(norm)) != n:
            raise ValueError(f"{self.cluster_id}: mentions not pre-merged")
        if len({m.gold for m in self.mentions}) < 2:
            raise ValueError(f"{self.cluster_id}: fewer than two gold entities")
        if not any(m.role_noun for m in self.mentions):
            raise ValueError(f"{self.cluster_id}: no role-noun mention")
        return self


def premerge_key(text: str) -> str:
    """DESIGN §5.7 default normaliser: NFC plus whitespace collapse, lossless on case."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


class HostileCase(Strict):
    """Probe 6: a probe 1 case with a team-written note advocating one wrong option."""

    case_id: str
    base_case_id: str
    style: Literal["A", "B"]
    advocated_text: str
    note: str
    insert_at: int = Field(ge=0)


class SingleCase(Strict):
    """Probe 8: one candidate offered alone as choice([c0, none_of_these])."""

    case_id: str
    set: Literal["lone_correct", "lone_wrong", "lone_partial", "partial_only"]
    doc_id: str
    field_id: str
    field_type: str
    label: str = Field(min_length=3)
    span: Span
    constructed: bool = False
    group: str

    @model_validator(mode="after")
    def _constructed_only_partial(self):
        if self.constructed and self.set != "lone_partial":
            raise ValueError(f"{self.case_id}: only lone partials may be constructed")
        return self


class ScreenDoc(Strict):
    """Probe 6 benign set: an unmodified document containing an ordinary processing note."""

    doc_id: str
    note_quote: str = Field(min_length=3)


# ---------------------------------------------------------------- loading

def load_manifest(root: pathlib.Path = CORPUS) -> dict[str, DocRecord]:
    docs = {}
    for line in (root / "manifest.jsonl").read_text().splitlines():
        d = DocRecord.model_validate_json(line)
        if d.doc_id in docs:
            raise ValueError(f"duplicate document id {d.doc_id}")
        docs[d.doc_id] = d
    return docs


def doc_text(rec: DocRecord, root: pathlib.Path = CORPUS) -> str:
    return (root / rec.path).read_text(encoding="utf-8")


def _lines(path: pathlib.Path) -> list[str]:
    return [ln for ln in path.read_text().splitlines() if ln.strip()]


def _unique(ids: list[str], what: str) -> None:
    seen = set()
    for i in ids:
        if i in seen:
            raise ValueError(f"duplicate {what} id {i}")
        seen.add(i)


def load_selection(path: pathlib.Path, root: pathlib.Path = CORPUS) -> list[SelectionCase]:
    docs = load_manifest(root)
    cases = [SelectionCase.model_validate_json(ln) for ln in _lines(path)]
    _unique([c.case_id for c in cases], "case")
    for c in cases:
        if c.doc_id not in docs:
            raise ValueError(f"{c.case_id}: unknown document {c.doc_id}")
        text = doc_text(docs[c.doc_id], root)
        _check_spans_against(text, c.options + c.removed, c.case_id)
    return cases


def load_clusters(path: pathlib.Path, root: pathlib.Path = CORPUS) -> list[Cluster]:
    docs = load_manifest(root)
    clusters = [Cluster.model_validate_json(ln) for ln in _lines(path)]
    _unique([c.cluster_id for c in clusters], "cluster")
    for c in clusters:
        if c.doc_id not in docs:
            raise ValueError(f"{c.cluster_id}: unknown document {c.doc_id}")
        text = doc_text(docs[c.doc_id], root)
        if c.passage_end > len(text):
            raise ValueError(f"{c.cluster_id}: passage beyond the document")
        for m in c.mentions:
            for s, e in m.spans:
                if not (c.passage_start <= s < e <= c.passage_end) or text[s:e] != m.text:
                    raise ValueError(f"{c.cluster_id}: mention {m.id} span [{s},{e}) does not reproduce its text")
    return clusters


def load_single(path: pathlib.Path, root: pathlib.Path = CORPUS) -> list[SingleCase]:
    docs = load_manifest(root)
    cases = [SingleCase.model_validate_json(ln) for ln in _lines(path)]
    _unique([c.case_id for c in cases], "case")
    for c in cases:
        if c.doc_id not in docs:
            raise ValueError(f"{c.case_id}: unknown document {c.doc_id}")
        _check_spans_against(doc_text(docs[c.doc_id], root), [c.span], c.case_id)
    return cases


def load_hostile(path: pathlib.Path, base: dict[str, SelectionCase], root: pathlib.Path = CORPUS) -> list[HostileCase]:
    docs = load_manifest(root)
    cases = [HostileCase.model_validate_json(ln) for ln in _lines(path)]
    _unique([c.case_id for c in cases], "case")
    for c in cases:
        b = base.get(c.base_case_id)
        if b is None or b.probe != "p1p3":
            raise ValueError(f"{c.case_id}: base case must be a probe 1 case")
        if c.advocated_text not in {o.text for o in b.options if o.label == "wrong"}:
            raise ValueError(f"{c.case_id}: the advocated text must be a wrong option of the base case")
        if c.insert_at > len(doc_text(docs[b.doc_id], root)):
            raise ValueError(f"{c.case_id}: insertion point beyond the document")
    return cases


def load_screen(path: pathlib.Path, root: pathlib.Path = CORPUS) -> list[ScreenDoc]:
    docs = load_manifest(root)
    items = [ScreenDoc.model_validate_json(ln) for ln in _lines(path)]
    _unique([s.doc_id for s in items], "screen document")
    for s in items:
        if s.doc_id not in docs:
            raise ValueError(f"unknown document {s.doc_id}")
        if s.note_quote not in doc_text(docs[s.doc_id], root):
            raise ValueError(f"{s.doc_id}: the quoted processing note is not in the document")
    return items


def dump(models: Iterable[BaseModel], path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(m.model_dump_json() + "\n" for m in models))


def raw_json(path: pathlib.Path):  # small helper for label and extraction files
    return json.loads(path.read_text())


__all__ = ["DocRecord", "Span", "Option", "SelectionCase", "Mention", "Cluster", "HostileCase", "SingleCase",
           "ScreenDoc", "load_manifest", "doc_text", "load_selection", "load_clusters", "load_single",
           "load_hostile", "load_screen", "premerge_key", "dump", "raw_json", "ValidationInfo"]
