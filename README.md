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
