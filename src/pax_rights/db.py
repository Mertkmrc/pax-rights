"""Postgres connection and schema."""

import os
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
DEFAULT_URL = "postgresql://pax:pax@localhost:5432/pax"


def connect() -> psycopg.Connection:
    # Autocommit, so `with conn.transaction():` blocks are real transactions, not savepoints.
    conn = psycopg.connect(os.environ.get("DATABASE_URL", DEFAULT_URL), autocommit=True)
    # register_vector looks up the vector type, so the extension has to exist first.
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


def apply_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA.read_text())
