"""Voyage embeddings behind a Postgres cache: sha256(text) -> vector, per model and input type."""

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Literal

import numpy as np
import psycopg
import voyageai

from pax_rights.ingest.chunk import approx_tokens

MODEL = "voyage-4"
PRICE_PER_M_TOKENS = 0.06  # USD for voyage-4 once the free 200M tokens are used up


def _limits() -> tuple[int, int]:
    """(tokens, requests) per minute. Read at call time, after .env is loaded.

    Defaults are Voyage's limits without a payment method. With a card on the
    account, raise both in .env (e.g. VOYAGE_TPM=3000000, VOYAGE_RPM=2000).
    """
    return int(os.environ.get("VOYAGE_TPM", 10_000)), int(os.environ.get("VOYAGE_RPM", 3))


InputType = Literal["document", "query"]


@dataclass
class EmbedStats:
    cached: int = 0
    embedded: int = 0
    tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return self.tokens / 1_000_000 * PRICE_PER_M_TOKENS


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed(
    conn: psycopg.Connection, texts: list[str], input_type: InputType, stats: EmbedStats
) -> list[np.ndarray]:
    """One vector per text, in order. Only texts missing from the cache hit the API."""
    hashes = [content_hash(t) for t in texts]
    rows = conn.execute(
        "SELECT content_hash, embedding FROM embedding_cache"
        " WHERE model = %s AND input_type = %s AND content_hash = ANY(%s)",
        (MODEL, input_type, list(set(hashes))),
    ).fetchall()
    vectors = dict(rows)
    missing = list({h: t for h, t in zip(hashes, texts, strict=True) if h not in vectors}.items())
    stats.cached += len(set(hashes)) - len(missing)

    if missing:
        client = voyageai.Client()  # reads VOYAGE_API_KEY
        tpm, rpm = _limits()
        # approx_tokens undercounts real tokens (Turkish especially), so each request
        # gets about half of the per-minute budget.
        batches = _batches(missing, budget=tpm // 2)
        for n, batch in enumerate(batches, start=1):
            result = _embed_with_retry(client, [t for _, t in batch], input_type)
            new = {
                h: np.array(v, dtype=np.float32)
                for (h, _), v in zip(batch, result.embeddings, strict=True)
            }
            # Store each batch as soon as it is paid for, so a later failure doesn't waste it.
            with conn.transaction(), conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO embedding_cache (model, input_type, content_hash, embedding)"
                    " VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    [(MODEL, input_type, h, v) for h, v in new.items()],
                )
            vectors.update(new)
            stats.embedded += len(batch)
            stats.tokens += result.total_tokens
            if n < len(batches):
                # Stay under both limits: this batch's share of the minute's token budget,
                # and at least 60/RPM seconds between requests.
                wait = max(60 / rpm, result.total_tokens / tpm * 60)
                print(
                    f"  batch {n}/{len(batches)}: {result.total_tokens} tokens, next in {wait:.0f}s"
                )
                time.sleep(wait)

    return [vectors[h] for h in hashes]


def _batches(items: list[tuple[str, str]], budget: int) -> list[list[tuple[str, str]]]:
    batches, current, tokens = [], [], 0
    for item in items:
        size = approx_tokens(item[1])
        if current and tokens + size > budget:
            batches.append(current)
            current, tokens = [], 0
        current.append(item)
        tokens += size
    if current:
        batches.append(current)
    return batches


def _embed_with_retry(client: voyageai.Client, texts: list[str], input_type: InputType, tries=5):
    for attempt in range(1, tries + 1):
        try:
            # truncation=False: fail loudly instead of silently embedding a cut-off text.
            return client.embed(texts, model=MODEL, input_type=input_type, truncation=False)
        except voyageai.error.RateLimitError:
            if attempt == tries:
                raise
            print(f"  rate limited, waiting 60s (attempt {attempt}/{tries})")
            time.sleep(60)
