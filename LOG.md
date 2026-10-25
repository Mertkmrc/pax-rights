# Log

One question per session at the start, the answer (and a number if there is one) at the end.

## 2026-10-25

**Question:** Does the scaffold run from a clean clone (`docker compose up`, `uv run pytest`, CI)?

**Answer:**
 Yes
## H1 · 2026-10-25 → Ingestion

**Week question:** For this corpus, does structure-based chunking (by article) or fixed-size chunking give better results?

**Parse (Claude):** `uv run python -m pax_rights.ingest.parse` → 8 docs, 336 records, ~1.02M chars in `data/processed/`. Repeating headers/footers stripped, line-break hyphenation joined, Pegasus split by `<h3>` section.

**Parse check (by hand, 5 pages per doc):**
