"""H1 gate: does each hand-written question find a relevant chunk in the top 5?

Usage: uv run python scripts/gate_test.py   (after python -m pax_rights.ingest)

A hit is a returned chunk from an expected document whose `covers` contains the
expected article, so a fixed-size chunk that starts in Art. 6 and runs into Art. 7
counts for an Art. 7 question.
"""

import json
from pathlib import Path

from dotenv import load_dotenv

from pax_rights.db import connect
from pax_rights.embed import MODEL, EmbedStats, embed
from pax_rights.ingest.chunk import STRATEGIES

GATE = Path(__file__).resolve().parent.parent / "eval" / "h1_gate.jsonl"
K = 5

SEARCH = """
SELECT doc_id, article, covers, page, embedding <=> %s AS distance
FROM chunks
WHERE strategy = %s AND embedding_model = %s
ORDER BY distance
LIMIT %s
"""


def main() -> None:
    load_dotenv()
    questions = [json.loads(line) for line in GATE.read_text(encoding="utf-8").splitlines()]
    stats = EmbedStats()
    with connect() as conn:
        vectors = embed(conn, [q["question"] for q in questions], "query", stats)
        summary = {}
        for strategy in STRATEGIES:
            print(f"\n=== {strategy}")
            ranks = []
            for q, vector in zip(questions, vectors, strict=True):
                rows = conn.execute(SEARCH, (vector, strategy, MODEL, K)).fetchall()
                expected = {(doc, article) for doc, article in q["expected_sources"]}
                relevant = [
                    any((doc, a) in expected for a in covers) for doc, _, covers, _, _ in rows
                ]
                hit = relevant.index(True) + 1 if any(relevant) else None
                ranks.append(hit)
                print(f"{'HIT ' if hit else 'MISS'} {q['id']} (rank {hit or '-'}) {q['question']}")
                for rank, (row, ok) in enumerate(zip(rows, relevant, strict=True), start=1):
                    doc, article, covers, page, distance = row
                    print(
                        f"   {'*' if ok else ' '}{rank}. {distance:.3f}  {doc}  art {article}  "
                        f"covers {covers}  p{page}"
                    )
            summary[strategy] = ranks
    print(f"\nTop-{K} hits (gate: at least 2 of 3; here out of {len(questions)}):")
    for strategy, ranks in summary.items():
        found = [r for r in ranks if r]
        mrr = sum(1 / r for r in found) / len(ranks)
        print(f"  {strategy:10} {len(found)}/{len(ranks)}   MRR {mrr:.2f}")
    print(f"query embeddings: {stats.cached} from cache, {stats.embedded} new")


if __name__ == "__main__":
    main()
