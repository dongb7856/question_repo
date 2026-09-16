#!/usr/bin/env python3
"""按顺序执行 scripts/db/migrations/*.sql。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from db.connection import connect, init_schema  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def run_migrations() -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("无 migration 文件")
        return

    with connect() as conn:
        init_schema(conn)
        with conn.cursor() as cur:
            for path in files:
                sql = path.read_text(encoding="utf-8")
                print(f">> 执行 migration: {path.name}")
                cur.execute(sql)
        conn.commit()

    print(f"完成: {len(files)} 个 migration")


if __name__ == "__main__":
    run_migrations()
