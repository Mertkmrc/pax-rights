# Log

One question per session at the start, the answer (and a number if there is one) at the end.

## 2026-10-25

**Question:** Does the scaffold run from a clean clone (`docker compose up`, `uv run pytest`, CI)?

**Answer:**
 Yes
## H1 · 2026-10-25 → Ingestion

**Week question:** For this corpus, does structure-based chunking (by article) or fixed-size chunking give better results?

**Parse (Claude):** `uv run python -m pax_rights.ingest.parse` → 8 docs, 336 records, ~1.02M chars in `data/processed/`. Repeating headers/footers stripped, line-break hyphenation joined, Pegasus split by `<h3>` section.

**Parse check (Claude, scripted: raw vs. cleaned lines, heading sequences, leftover characters):**

- Fixed: paragraph numbers on their own line at a page edge ("2." in EU261) were stripped as page numbers, because "2." and "3." collapse to the same digit-normalized shape. Enumerators are now exempt.
- Fixed: symbol-font bullets (U+F0B7 in THY EN, Wizz) become "•"; web icons (U+EACA in the Lufthansa print) and zero-width spaces are dropped.
- Article headings are complete and in ascending order in every PDF: THY EN 16, THY TR 18, Lufthansa 17, Wizz 24 top-level sections, EU261 19, SHY-Yolcu 22. So EU261's two-column layout is read in the right order.
- Articles cross page boundaries (THY Art. 1 spans pp. 1-2). Structure-based chunking has to join pages first, then split on headings.
- Lufthansa: replaced the browser print (27 pp., site navigation and footer on every page) with the official PDF linked from the same page (August 2026 edition, 17 pp.). That URL is not behind the bot check, so the source is now `fetch: auto`. Page 1 is still a table of contents listing all 17 "Article N:" headings, which the chunker has to skip.
- Fixed: line-break dehyphenation turned real compounds into one word ("check-\nin" -> "checkin"). A hyphen now stays when the hyphenated form appears unbroken elsewhere in the same document. Known miss: "flight-related" appears only once, broken, so it still becomes "flightrelated".
- THY EN has 16 articles, TR 18: the 2025 English and 2019 Turkish texts are structurally different versions, not translations of each other.
- Pegasus: TR has one section EN lacks (7.3, items accepted in the cabin). Top-level sections 2 (privacy policy) and 14 (BolBol loyalty terms) are not passenger rights; candidates to exclude at chunking time.
- Left as is (low impact): EU261 page header "L 46/N" and OJ footnotes at page ends; THY TR trailing footnote markers.

**Chunking (Claude, at Mert's request; both strategies share `Document -> list[Chunk]`):** `uv run python -m pax_rights.ingest.chunk`

| Strategy | Chunks | Avg tokens* | Max tokens* |
|---|---|---|---|
| fixed (500, overlap 50) | 405 | 495 | 500 |
| structure (per article, windowed above 800) | 513 | 371 | 788 |

\* Approximate (words + punctuation). Real counts come from Voyage at embedding time.

Structure-based keeps every EU261 article intact (Art. 7 = one chunk); fixed-size labels each chunk with the article it starts in, so both can be cited. Which retrieves better is still open: that needs the gate test (3 questions) now, and the eval set in H3.
