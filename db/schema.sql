-- Applied at the start of every ingest run, so every statement must be safe to re-run.
-- documents and chunks can be rebuilt from data/raw/ at any time; embedding_cache
-- cannot without paying for the API calls again, so never drop it casually.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per source in data/sources.yaml. Citations take title and url from here.
CREATE TABLE IF NOT EXISTS documents (
    doc_id       text PRIMARY KEY,
    title        text NOT NULL,
    publisher    text NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('airline', 'regulation')),
    jurisdiction text NOT NULL CHECK (jurisdiction IN ('EU', 'TR')),
    lang         text NOT NULL CHECK (lang IN ('en', 'tr')),
    url          text NOT NULL,
    retrieved    date
);

-- Both chunking strategies live side by side; every query filters on strategy.
-- Ingest is idempotent by replacing all rows of one (strategy, doc_id) in a transaction.
CREATE TABLE IF NOT EXISTS chunks (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    strategy        text NOT NULL CHECK (strategy IN ('fixed', 'structure')),
    doc_id          text NOT NULL REFERENCES documents ON DELETE CASCADE,
    chunk_no        int  NOT NULL,
    article         text,  -- '7', '5.2'; NULL for text before the first article
    page            int,   -- page the chunk starts on; NULL for HTML sources
    text            text NOT NULL,
    embedding_model text NOT NULL,  -- queries must be embedded with the same model
    embedding       vector(1024) NOT NULL,
    tsv             tsvector,  -- H4: full-text half of hybrid search, filled later
    UNIQUE (strategy, doc_id, chunk_no)
);

-- sha256(text) -> vector, per model and input type. Queries are cached too, so
-- re-running the eval set does not pay for the same questions twice.
CREATE TABLE IF NOT EXISTS embedding_cache (
    model        text NOT NULL,
    input_type   text NOT NULL CHECK (input_type IN ('document', 'query')),
    content_hash text NOT NULL,
    embedding    vector(1024) NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model, input_type, content_hash)
);

-- No vector index yet. At ~900 rows an exact scan is fast and returns the true top k,
-- which keeps the eval baseline clean. HNSW comes later, with its effect measured.
