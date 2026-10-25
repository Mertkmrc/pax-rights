# pax-rights

An assistant that answers airline passenger-rights and fare-rule questions from the source texts, with a citation for every claim.

> **Status: in progress.** Nothing here is production-ready yet. Progress notes live in [`LOG.md`](LOG.md).

## The problem

"My flight was delayed 4 hours, am I owed compensation?" and "Can I change an Economy Light ticket, and what does it cost?" sound simple. The answers are spread across documents that disagree with each other:

- airline Conditions of Carriage and fare-family rule tables,
- EU Regulation 261/2004,
- Turkey's SHGM passenger-rights regulation (SHY-Yolcu).

Which one applies depends on the route, the direction of travel, and the operating carrier. A useful assistant has to:

1. **cite** the exact article it relies on,
2. **say "I don't know"** when the corpus doesn't cover the question,
3. **show both answers** when two jurisdictions overlap instead of silently picking one.

Every retrieval and answer change is measured against a hand-written evaluation set.

## Stack

Python 3.12 (uv, ruff, pytest) · FastAPI · Postgres + pgvector · Voyage embeddings and rerank · Claude

## Why it's built this way

### Chunking by article

I chunk by article, cutting articles over 800 tokens into overlapping windows. The alternative was fixed 500-token windows with a 50-token overlap.

Both find the text. On the 8-question H1 gate, a relevant chunk reached the top 5 for 8/8 questions with fixed windows and 6/8 with article chunks, at nearly the same MRR (0.68 vs 0.69). But a fixed chunk spans 1.8 articles on average and carries the label of the article it starts in. Scored by that label, the one an answer cites, fixed drops to 5/8 with MRR 0.28. Every claim here cites `[doc, article]`, so the chunk boundary should be the citation boundary.

The cost: one heading rule per document, so each new airline needs its own pattern. Of the two misses, one label looks too narrow; in the other, the airline's name barely moved the vector, which calls for an airline filter or BM25. If fixed windows win recall@5 on the golden set, I switch.

## Run locally

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```sh
cp .env.example .env          # add your API keys
docker compose up -d --wait   # Postgres + pgvector
uv sync
uv run pytest
uv run uvicorn pax_rights.api:app --reload
```

## Corpus

Public documents only. Raw files are not committed; see [`data/README.md`](data/README.md).

## License

MIT
