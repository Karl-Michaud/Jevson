"""The real candidate extractor for probes 1-3 (docs/taxonomy.md §2.2 item 3, §3.3).

Candidates are the union of (a) pattern extractors for the field's value type and (b) the recorded output of the
LLM extractor. Every candidate text is located in the source by exact match; unlocatable texts are rejected and
counted; every occurrence becomes an option. An occurrence must not sit inside a longer word or number: if the
text begins (ends) with a letter or digit, the character before (after) it must not be one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MONTHS_EN = ("January|February|March|April|May|June|July|August|September|October|November|December|"
             "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
MONTHS_ES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
_M = f"(?:{MONTHS_EN})\\.?"
_ORD = r"\d{1,2}(?:st|nd|rd|th)?"

PATTERNS: dict[str, list[str]] = {
    "money": [
        r"(?:US\$|USD|EUR|IDR|Rp\.?|[$€£¥])\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?(?:\s?(?:million|billion))?",
        r"(?<![\d.,])\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?(?!\d|[.,]\d)",
        r"(?<![\d.,])\d+[.,]\d{2}(?!\d|[.,]\d)",
    ],
    "date": [
        rf"{_M}\s{_ORD},?\s\d{{4}}",
        rf"{_ORD}\s(?:day\sof\s)?{_M},?\s\d{{4}}",
        rf"(?i:{_ORD}\sde\s(?:{MONTHS_ES})(?:\sde(?:l)?\s\d{{4}})?)",
        r"(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?!\d)",
        r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)",
        rf"{_M}\s\d{{4}}",
    ],
    "year": [r"(?<!\d)(?:19|20)\d{2}(?!\d)"],
    "duration": [
        r"(?i)\b(?:\w+\s\()?\d+\)?\s(?:business\s|calendar\s)?(?:days?|weeks?|months?|years?)\b",
        r"(?i)\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|thirty|sixty|ninety)"
        r"(?:\s\(\d+\))?\s(?:business\s|calendar\s)?(?:days?|weeks?|months?|years?)\b",
    ],
    "number": [r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])"],
    "email": [r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"],
    "phone": [r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?:\s?(?:x|ext\.?)\s?\d+)?"],
    "url": [r"https?://[^\s<>()\"']+[^\s<>()\"'.,;:]"],
    "version": [r"(?<![\w.])v?\d+(?:\.\d+){1,3}(?:[-.]?(?:beta|rc|alpha)\d*)?(?![\w])"],
    "text": [],
}


def pattern_candidates(source: str, value_type: str) -> list[str]:
    """Distinct matched texts, in order of first match."""
    if value_type not in PATTERNS:
        raise ValueError(f"unknown value type {value_type!r}")
    seen: dict[str, None] = {}
    for pat in PATTERNS[value_type]:
        for m in re.finditer(pat, source):
            t = m.group(0).strip()
            if t:
                seen.setdefault(t, None)
    return list(seen)


def _boundary_ok(source: str, start: int, end: int) -> bool:
    if source[start].isalnum() and start > 0 and source[start - 1].isalnum():
        return False
    if source[end - 1].isalnum() and end < len(source) and source[end].isalnum():
        return False
    return True


def locate(source: str, text: str) -> list[tuple[int, int]]:
    """Every occurrence of text by exact match (overlapping included), subject to the word-boundary rule."""
    if not text:
        return []
    out, i = [], source.find(text)
    while i >= 0:
        if _boundary_ok(source, i, i + len(text)):
            out.append((i, i + len(text)))
        i = source.find(text, i + 1)
    return out


@dataclass
class Extraction:
    texts: list[str]                                   # distinct located candidate texts
    options: list[tuple[int, int]]                     # every occurrence, in source order
    by_extractor: dict[str, list[str]] = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)  # texts that could not be located


def extract(source: str, value_type: str, llm_texts: list[str]) -> Extraction:
    pat = pattern_candidates(source, value_type)
    llm = [t for t in dict.fromkeys(t.strip() for t in llm_texts) if t]
    texts, rejected, by = [], [], {"pattern": [], "llm": []}
    for name, group in (("pattern", pat), ("llm", llm)):
        for t in group:
            if locate(source, t):
                by[name].append(t)
                if t not in texts:
                    texts.append(t)
            elif name == "llm":
                rejected.append(t)
    spans = sorted({sp for t in texts for sp in locate(source, t)})
    return Extraction(texts, spans, by, rejected)
