"""Load the corpus into Postgres: documents, chunks of both strategies, embeddings.

Usage: uv run python -m pax_rights.ingest   (after fetch_corpus.py and ingest.parse)

Idempotent: each (strategy, doc_id) is deleted and re-inserted in one transaction,
and vectors come from embedding_cache whenever the same text was embedded before.
"""

import yaml
from dotenv import load_dotenv

from pax_rights.db import apply_schema, connect
from pax_rights.embed import MODEL, EmbedStats, embed
from pax_rights.ingest.chunk import SOURCES, STRATEGIES, load_documents

INSERT_CHUNK = """
INSERT INTO chunks
    (strategy, doc_id, chunk_no, article, covers, page, text, embedding_model, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

UPSERT_DOCUMENT = """
INSERT INTO documents (doc_id, title, publisher, kind, jurisdiction, lang, url, retrieved)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (doc_id) DO UPDATE SET
    title = EXCLUDED.title, publisher = EXCLUDED.publisher, kind = EXCLUDED.kind,
    jurisdiction = EXCLUDED.jurisdiction, lang = EXCLUDED.lang, url = EXCLUDED.url,
    retrieved = EXCLUDED.retrieved
"""


def main() -> None:
    load_dotenv()
    docs = load_documents()
    loaded = {doc.doc_id for doc in docs}
    sources = [s for s in yaml.safe_load(SOURCES.read_text())["sources"] if s["id"] in loaded]
    stats = EmbedStats()

    with connect() as conn:
        apply_schema(conn)
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                UPSERT_DOCUMENT,
                [
                    (
                        s["id"],
                        s["title"],
                        s["publisher"],
                        s["kind"],
                        s["jurisdiction"],
                        s["lang"],
                        s["url"],
                        s.get("retrieved"),
                    )
                    for s in sources
                ],
            )

        for name, strategy in STRATEGIES.items():
            chunks = [chunk for doc in docs for chunk in strategy(doc)]
            vectors = embed(conn, [c.text for c in chunks], "document", stats)
            rows = [
                (name, c.doc_id, c.chunk_no, c.article, c.covers, c.page, c.text, MODEL, v)
                for c, v in zip(chunks, vectors, strict=True)
            ]
            for doc in docs:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM chunks WHERE strategy = %s AND doc_id = %s", (name, doc.doc_id)
                    )
                    cur.executemany(INSERT_CHUNK, [r for r in rows if r[1] == doc.doc_id])

        counts = conn.execute(
            "SELECT strategy, count(*) FROM chunks GROUP BY strategy ORDER BY strategy"
        ).fetchall()

    print(f"documents: {len(sources)}")
    for name, n in counts:
        print(f"chunks ({name}): {n}")
    print(
        f"embeddings: {stats.cached} from cache, {stats.embedded} new "
        f"({stats.tokens:,} tokens, ${stats.cost_usd:.4f} at list price; free tier covers it)"
    )


if __name__ == "__main__":
    main()
