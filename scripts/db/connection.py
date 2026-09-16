"""PostgreSQL 连接配置。"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).resolve().parent / "schema.sql"

DEFAULT_DB = os.environ.get("QUESTION_REPO_DB", "question_repo")
DEFAULT_HOST = os.environ.get("PGHOST", "127.0.0.1")
DEFAULT_PORT = os.environ.get("PGPORT", "5432")
DEFAULT_USER = os.environ.get("PGUSER", os.environ.get("USER", "postgres"))
DEFAULT_PASSWORD = os.environ.get("PGPASSWORD", "")


def connect(dbname: str | None = None) -> psycopg.Connection:
    kwargs: dict[str, str] = {
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "user": DEFAULT_USER,
        "dbname": dbname or DEFAULT_DB,
    }
    if DEFAULT_PASSWORD:
        kwargs["password"] = DEFAULT_PASSWORD
    return psycopg.connect(**kwargs)


def init_schema(conn: psycopg.Connection) -> None:
    sql = SCHEMA.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
