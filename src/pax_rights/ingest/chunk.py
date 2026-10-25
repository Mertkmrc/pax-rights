"""Parsed documents (data/processed/) -> chunks (data/chunks/<strategy>.jsonl).

Usage: uv run python -m pax_rights.ingest.chunk [--strategy fixed|structure|all]

Two strategies with the same signature, Document -> list[Chunk], so embedding and
eval can swap one for the other:

  fixed      ~500-token windows with 50 tokens of overlap, blind to structure.
  structure  one chunk per article; an article longer than MAX_TOKENS is cut
             into windows the same way `fixed` cuts a whole document.

Both label every chunk with the page and article it starts in, so a citation
works with either strategy. Where the articles are is decided once, when the
Document is built (HEADING_RULES); the strategies only decide where to cut.
"""

import argparse
import bisect
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "data" / "sources.yaml"
PROCESSED = ROOT / "data" / "processed"
CHUNKS = ROOT / "data" / "chunks"

SIZE = 500
OVERLAP = 50
MAX_TOKENS = 800


class Chunk(BaseModel):
    doc_id: str
    chunk_no: int
    source: Literal["airline", "regulation"]
    jurisdiction: Literal["EU", "TR"]
    lang: Literal["en", "tr"]
    article: str | None  # "7", "5.2"; None for text before the first article
    covers: list[str]  # every article the text touches, e.g. ["6", "7"]; used to score hits
    page: int | None  # page the chunk starts on; None for HTML sources
    text: str


def approx_tokens(text: str) -> int:
    # Words and punctuation marks, a rough stand-in for model tokens. It only sizes
    # chunks; the real count comes back from the Voyage API at embedding time.
    return len(re.findall(r"\w+|[^\w\s]", text))


# --- Where the articles are (per document) -----------------------------------


@dataclass(frozen=True)
class HeadingRule:
    pattern: str  # matched against the start of a stripped line; group 1 = article number
    title_above: bool = False  # the article title is on the line before the heading


# From the parse check (LOG.md, H1). Pegasus needs no rule: its sections are
# already split by <h3> during parsing.
HEADING_RULES = {
    "thy-gcc-en": HeadingRule(r"ARTICLE (\d+)\b"),
    "thy-gcc-tr": HeadingRule(r"MADDE (\d+)\b"),
    "lufthansa-gcc-en": HeadingRule(r"Article (\d+):"),
    "wizz-gcc-en": HeadingRule(r"(\d+)\.\s*$"),
    "eu261": HeadingRule(r"Article (\d+)\s*$"),
    "shy-yolcu": HeadingRule(r"MADDE (\d+) –", title_above=True),
}


@dataclass
class Document:
    doc_id: str
    source: str
    jurisdiction: str
    lang: str
    text: str = ""
    # (char offset, value) marks, sorted by offset: "from here on, page/article is X".
    pages: list[tuple[int, int | None]] = field(default_factory=list)
    articles: list[tuple[int, str | None]] = field(default_factory=list)

    def page_at(self, offset: int) -> int | None:
        return _value_at(self.pages, offset)

    def article_at(self, offset: int) -> str | None:
        return _value_at(self.articles, offset)

    def articles_between(self, start: int, end: int) -> list[str]:
        """Articles whose text overlaps [start, end), in order."""
        labels = [self.article_at(start)] + [
            a for offset, a in self.articles if start < offset < end
        ]
        return list(dict.fromkeys(a for a in labels if a is not None))

    def article_bounds(self) -> list[int]:
        """Char offsets where each article (or the preamble) starts, plus the end."""
        return [offset for offset, _ in self.articles] + [len(self.text)]


def _value_at(marks: list[tuple[int, object]], offset: int):
    i = bisect.bisect_right([o for o, _ in marks], offset) - 1
    return marks[i][1] if i >= 0 else None


def _find_headings(lines: list[str], rule: HeadingRule) -> tuple[list[tuple[int, str]], range]:
    """(line where each article starts, article number), plus the table-of-contents lines."""
    found = [
        (i, m.group(1))
        for i, line in enumerate(lines)
        if (m := re.match(rule.pattern, line.strip()))
    ]
    if rule.title_above:
        found = [(max(i - 1, 0), number) for i, number in found]
    # A table of contents lists every heading once before the body (Lufthansa p.1).
    # If the first article number comes back later, everything before that is the TOC.
    toc = range(0)
    restart = max((k for k, (_, number) in enumerate(found) if number == found[0][1]), default=0)
    if restart:
        toc = range(found[0][0], found[restart][0])
        found = found[restart:]
    return found, toc


def _build(
    meta: dict,
    lines: list[tuple[int | None, str]],
    headings: list[tuple[int, str | None]],
    skip: range = range(0),
) -> Document:
    doc = Document(meta["id"], meta["kind"], meta["jurisdiction"], meta["lang"])
    starts = dict(headings)
    parts, offset = [], 0
    for i, (page, line) in enumerate(lines):
        if i in skip:
            continue
        if not doc.pages or doc.pages[-1][1] != page:
            doc.pages.append((offset, page))
        if i in starts:
            doc.articles.append((offset, starts[i]))
        parts.append(line)
        offset += len(line) + 1
    if not doc.articles or doc.articles[0][0] > 0:
        doc.articles.insert(0, (0, None))  # preamble
    doc.text = "\n".join(parts)
    return doc


def document_from_pdf(meta: dict, records: list[dict]) -> Document:
    lines = [(r["page"], line) for r in records for line in r["text"].splitlines()]
    headings, toc = _find_headings([line for _, line in lines], HEADING_RULES[meta["id"]])
    return _build(meta, lines, headings, skip=toc)


def document_from_html(meta: dict, records: list[dict]) -> Document:
    lines, headings = [], []
    for r in records:
        number = re.match(r"\d+(?:\.\d+)*", r["section"])
        headings.append((len(lines), number.group(0) if number else None))
        lines.append((None, r["section"]))
        lines.extend((None, line) for line in r["text"].splitlines())
    return _build(meta, lines, headings)


def load_documents() -> list[Document]:
    docs = []
    for meta in yaml.safe_load(SOURCES.read_text())["sources"]:
        path = PROCESSED / f"{meta['id']}.jsonl"
        if not path.exists():
            print(f"missing {path.name} (run python -m pax_rights.ingest.parse)")
            continue
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        build = document_from_pdf if meta["format"] == "pdf" else document_from_html
        docs.append(build(meta, records))
    return docs


# --- Where to cut (the two strategies) ---------------------------------------


def windows(text: str, start: int, end: int, size: int, overlap: int) -> list[tuple[int, int]]:
    """Char spans of ~size-token windows over text[start:end], cut at word boundaries.

    Each window after the first starts `overlap` tokens before the previous one ended.
    """
    words = [(m.start() + start, m.end() + start) for m in re.finditer(r"\S+", text[start:end])]
    weights = [approx_tokens(text[s:e]) for s, e in words]
    spans, i = [], 0
    while i < len(words):
        j, tokens = i, 0
        while j < len(words) and (tokens == 0 or tokens + weights[j] <= size):
            tokens += weights[j]
            j += 1
        spans.append((words[i][0], words[j - 1][1]))
        if j == len(words):
            break
        k, back = j, 0
        while k > i + 1 and back < overlap:
            k -= 1
            back += weights[k]
        i = k
    return spans


def _chunks(doc: Document, spans: list[tuple[int, int]]) -> list[Chunk]:
    chunks = []
    for start, end in spans:
        text = doc.text[start:end].strip()
        if not text:
            continue
        start += len(doc.text[start:end]) - len(doc.text[start:end].lstrip())
        chunks.append(
            Chunk(
                doc_id=doc.doc_id,
                chunk_no=len(chunks),
                source=doc.source,
                jurisdiction=doc.jurisdiction,
                lang=doc.lang,
                article=doc.article_at(start),
                covers=doc.articles_between(start, end),
                page=doc.page_at(start),
                text=text,
            )
        )
    return chunks


def fixed_chunks(doc: Document, size: int = SIZE, overlap: int = OVERLAP) -> list[Chunk]:
    return _chunks(doc, windows(doc.text, 0, len(doc.text), size, overlap))


def structure_chunks(
    doc: Document, max_tokens: int = MAX_TOKENS, size: int = SIZE, overlap: int = OVERLAP
) -> list[Chunk]:
    spans = []
    bounds = doc.article_bounds()
    for start, end in pairwise(bounds):
        if approx_tokens(doc.text[start:end]) <= max_tokens:
            spans.append((start, end))
        else:
            spans.extend(windows(doc.text, start, end, size, overlap))
    return _chunks(doc, spans)


Strategy = Callable[[Document], list[Chunk]]
STRATEGIES: dict[str, Strategy] = {"fixed": fixed_chunks, "structure": structure_chunks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strategy", choices=[*STRATEGIES, "all"], default="all")
    args = parser.parse_args()
    names = list(STRATEGIES) if args.strategy == "all" else [args.strategy]

    docs = load_documents()
    CHUNKS.mkdir(parents=True, exist_ok=True)
    for name in names:
        chunks = [chunk for doc in docs for chunk in STRATEGIES[name](doc)]
        out = CHUNKS / f"{name}.jsonl"
        out.write_text("".join(c.model_dump_json() + "\n" for c in chunks), encoding="utf-8")

        print(f"\n{name}: {len(chunks)} chunks -> {out.relative_to(ROOT)}")
        print(f"  {'doc':18} {'chunks':>6} {'avg tok':>8} {'max tok':>8}")
        for doc in docs:
            sizes = [approx_tokens(c.text) for c in chunks if c.doc_id == doc.doc_id]
            avg = sum(sizes) / len(sizes) if sizes else 0
            print(f"  {doc.doc_id:18} {len(sizes):6} {avg:8.0f} {max(sizes, default=0):8}")
        sizes = [approx_tokens(c.text) for c in chunks]
        print(f"  {'total':18} {len(sizes):6} {sum(sizes) / len(sizes):8.0f} {max(sizes):8}")


if __name__ == "__main__":
    main()
