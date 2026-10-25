import pytest

from pax_rights.ingest.chunk import (
    PROCESSED,
    approx_tokens,
    document_from_html,
    document_from_pdf,
    fixed_chunks,
    load_documents,
    structure_chunks,
    windows,
)

EU = {"id": "eu261", "kind": "regulation", "jurisdiction": "EU", "lang": "en"}


def pages(*texts):
    return [{"doc_id": EU["id"], "page": n, "text": t} for n, t in enumerate(texts, start=1)]


def test_windows_respect_size_and_overlap():
    text = " ".join(f"w{i}" for i in range(1200))  # one token per word
    spans = windows(text, 0, len(text), size=500, overlap=50)
    sizes = [approx_tokens(text[s:e]) for s, e in spans]
    assert sizes[:2] == [500, 500]
    first, second = (text[s:e].split() for s, e in spans[:2])
    assert first[-50:] == second[:50]


def test_structure_keeps_an_article_in_one_chunk_across_pages():
    doc = document_from_pdf(
        EU,
        pages(
            "Recital text.\nArticle 6\nDelay\nSix.",
            "Article 7\nRight to compensation\nSeven starts here",
            "and ends on the next page.\nArticle 8\nRe-routing",
        ),
    )
    chunks = structure_chunks(doc)
    assert [c.article for c in chunks] == [None, "6", "7", "8"]
    seven = chunks[2]
    assert seven.page == 2
    assert seven.text.startswith("Article 7") and seven.text.endswith("next page.")


def test_both_strategies_label_chunks_with_their_article():
    doc = document_from_pdf(EU, pages("Article 1\n" + "a " * 600, "Article 2\n" + "b " * 600))
    for chunks in (fixed_chunks(doc), structure_chunks(doc)):
        assert {c.article for c in chunks} == {"1", "2"}
        assert all(c.text.split()[-1] == "b" for c in chunks if c.article == "2")


def test_table_of_contents_is_dropped():
    lh = {"id": "lufthansa-gcc-en", "kind": "airline", "jurisdiction": "EU", "lang": "en"}
    doc = document_from_pdf(
        lh,
        pages(
            "GCC\nArticle 1: Terms\nArticle 2: Scope",
            "Article 1: Terms\nBody one.\nArticle 2: Scope\nBody two.",
        ),
    )
    assert [c.article for c in structure_chunks(doc)] == [None, "1", "2"]
    assert doc.text.count("Article 1: Terms") == 1


def test_title_above_heading_stays_with_its_article():
    shy = {"id": "shy-yolcu", "kind": "regulation", "jurisdiction": "TR", "lang": "tr"}
    doc = document_from_pdf(shy, pages("Amaç\nMADDE 1 – (1) Bir.\nKapsam\nMADDE 2 – (1) İki."))
    chunks = structure_chunks(doc)
    assert [c.text.splitlines()[0] for c in chunks] == ["Amaç", "Kapsam"]


def test_html_sections_become_articles():
    peg = {"id": "pegasus-rules-en", "kind": "airline", "jurisdiction": "TR", "lang": "en"}
    records = [
        {"doc_id": peg["id"], "page": None, "section": "Important information", "text": "Intro."},
        {"doc_id": peg["id"], "page": None, "section": "5.2. Ticket changes", "text": "Rules."},
    ]
    chunks = structure_chunks(document_from_html(peg, records))
    assert [(c.article, c.page) for c in chunks] == [(None, None), ("5.2", None)]


@pytest.mark.skipif(not (PROCESSED / "eu261.jsonl").exists(), reason="corpus not parsed")
def test_real_eu261_has_19_articles_and_article_7_is_one_chunk():
    eu261 = next(doc for doc in load_documents() if doc.doc_id == "eu261")
    chunks = structure_chunks(eu261)
    assert {c.article for c in chunks} - {None} == {str(n) for n in range(1, 20)}
    assert [c.article for c in chunks].count("7") == 1


def test_fixed_chunk_spanning_two_articles_covers_both():
    doc = document_from_pdf(EU, pages("Article 6\n" + "a " * 300 + "\nArticle 7\n" + "b " * 100))
    (chunk,) = fixed_chunks(doc)
    assert chunk.article == "6"
    assert chunk.covers == ["6", "7"]
