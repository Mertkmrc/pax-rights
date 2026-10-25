"""Raw corpus files (data/raw/) -> one JSONL per document (data/processed/).

Usage: uv run python -m pax_rights.ingest.parse

PDF records:  {"doc_id", "page", "text"}            one per page
HTML records: {"doc_id", "page": null, "section", "text"}  one per <h3> section

Line breaks are kept on purpose: structure-based chunking needs headings like
"Article 7" or "MADDE 17 –" to start on their own line.
"""

import json
import re
from collections import Counter
from pathlib import Path

import pymupdf
import yaml
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "data" / "sources.yaml"
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# Page headers/footers live in the first/last few lines of a page.
HEAD_LINES = 3
TAIL_LINES = 4
# A line counts as a header/footer if it shows up on at least this share of pages.
REPEAT_SHARE = 0.5


# Paragraph and section numbers ("2.", "(2)", "2.1", "5.7.10.") often sit on their own line
# at a page edge. They must never be mistaken for page numbers.
ENUMERATOR = re.compile(r"\(?\d+(\.\d+)*[.)]?")


def _shape(line: str) -> str:
    # "3 / 19" and "4 / 19" should count as the same line.
    line = line.strip()
    if ENUMERATOR.fullmatch(line) and not line.isdigit():
        return line
    return re.sub(r"\d+", "#", line)


def strip_repeating_lines(pages: list[list[str]], max_passes: int = 3) -> list[list[str]]:
    """Drop header/footer lines that repeat across most pages (page numbers, print stamps)."""
    if len(pages) < 3:
        return pages
    # Removing one footer can expose another: Lufthansa's browser print has a nav bar
    # right above the date/URL footer. Repeat until nothing changes.
    for _ in range(max_passes):
        cleaned = _strip_edges_once(pages)
        if cleaned == pages:
            break
        pages = cleaned
    return pages


def _strip_edges_once(pages: list[list[str]]) -> list[list[str]]:
    counts = Counter()
    for lines in pages:
        edge = lines[:HEAD_LINES] + lines[-TAIL_LINES:]
        counts.update({_shape(line) for line in edge})
    threshold = REPEAT_SHARE * len(pages)
    repeated = {shape for shape, n in counts.items() if n >= threshold}

    cleaned = []
    for lines in pages:
        head = [ln for ln in lines[:HEAD_LINES] if _shape(ln) not in repeated]
        body = lines[HEAD_LINES:-TAIL_LINES] if len(lines) > HEAD_LINES + TAIL_LINES else []
        tail_start = max(HEAD_LINES, len(lines) - TAIL_LINES)
        tail = [ln for ln in lines[tail_start:] if _shape(ln) not in repeated]
        cleaned.append(head + body + tail)
    return cleaned


def hyphenated_words(text: str) -> set[str]:
    """Hyphenated compounds that appear unbroken somewhere in the text ("check-in")."""
    return {w.lower() for w in re.findall(r"\w+(?:-\w+)+", text)}


def dehyphenate(text: str, compounds: set[str] = frozenset()) -> str:
    """Join words split across lines: "trans-\\nported" -> "transported".

    Only when the next line starts lowercase, so "non-\\nEU" keeps its hyphen. If the
    hyphenated form is a known compound ("check-in"), the hyphen stays.
    """

    def join(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        if f"{left}-{right}".lower() in compounds:
            return f"{left}-{right}"
        return left + right

    return re.sub(r"(\w+)-\n([a-zçğıöşüâîû]\w*)", join, text)


# Symbol-font bullets come out as private-use code points; anything else in that
# range is a web icon (Lufthansa's print). Zero-width spaces carry no text.
BULLETS = str.maketrans({"\uf0b7": "\u2022", "\uf0a7": "\u2022"})
ICONS = re.compile("[\ue000-\uf8ff\u200b]")


def clean_line(line: str) -> str:
    return ICONS.sub("", line.translate(BULLETS)).rstrip()


def parse_pdf(path: Path, doc_id: str) -> list[dict]:
    with pymupdf.open(path) as doc:
        pages = [
            [clean_line(line) for line in page.get_text().splitlines() if clean_line(line).strip()]
            for page in doc
        ]
    pages = strip_repeating_lines(pages)
    compounds = hyphenated_words("\n".join(line for lines in pages for line in lines))
    return [
        {"doc_id": doc_id, "page": number, "text": dehyphenate("\n".join(lines), compounds)}
        for number, lines in enumerate(pages, start=1)
        if lines
    ]


def parse_html(path: Path, doc_id: str) -> list[dict]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    # Pegasus keeps the whole document in one accordion; everything else is site chrome.
    content = soup.select_one("section.faq-acc")
    if content is None:
        raise ValueError(f"{path.name}: content container not found, page layout changed?")
    for tag in content(["script", "style", "noscript", "svg", "button"]):
        tag.decompose()

    records = []
    section, parts = None, []

    def flush() -> None:
        if section is not None and parts:
            records.append(
                {"doc_id": doc_id, "page": None, "section": section, "text": "\n".join(parts)}
            )

    for node in content.descendants:
        if isinstance(node, Tag) and node.name == "h3":
            flush()
            section, parts = " ".join(node.get_text().split()), []
        elif (
            isinstance(node, NavigableString)
            and not isinstance(node, Comment)
            and node.strip()
            and node.find_parent("h3") is None
        ):
            parts.append(node.strip())
    flush()
    return records


def main() -> None:
    sources = yaml.safe_load(SOURCES.read_text())["sources"]
    PROCESSED.mkdir(parents=True, exist_ok=True)
    for src in sources:
        path = RAW / f"{src['id']}.{src['format']}"
        if not path.exists():
            print(f"missing {path.name} (run scripts/fetch_corpus.py)")
            continue
        parse = parse_pdf if src["format"] == "pdf" else parse_html
        records = parse(path, src["id"])
        out = PROCESSED / f"{src['id']}.jsonl"
        with out.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        chars = sum(len(r["text"]) for r in records)
        print(f"{src['id']:20} {len(records):4} records {chars:8} chars")


if __name__ == "__main__":
    main()
