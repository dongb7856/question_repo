#!/usr/bin/env python3
"""查询已入库的真题。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from db.connection import connect  # noqa: E402


def source_clause(source: str | None) -> tuple[str, list[object]]:
    if source == "bb":
        return " AND p.source_file LIKE 'bb/%'", []
    if source == "web":
        return " AND p.source_file NOT LIKE 'bb/%'", []
    return "", []


def search(
    keyword: str,
    subject: str | None,
    year: int | None,
    limit: int,
    source: str | None = None,
) -> None:
    sql = """
        SELECT s.name, p.year, q.number, q.question_type, q.stem, q.options, q.answer,
               p.source_file
        FROM questions q
        JOIN exam_papers p ON p.id = q.exam_paper_id
        JOIN subjects s ON s.id = p.subject_id
        WHERE q.stem ILIKE %s
    """
    params: list[object] = [f"%{keyword}%"]

    if subject:
        sql += " AND s.name = %s"
        params.append(subject)
    if year:
        sql += " AND p.year = %s"
        params.append(year)
    src_sql, src_params = source_clause(source)
    sql += src_sql
    params.extend(src_params)

    sql += " ORDER BY s.name, p.year, q.number LIMIT %s"
    params.append(limit)

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        print("未找到匹配题目")
        return

    for subj, yr, num, qtype, stem, options, answer, source_file in rows:
        src = "bb" if source_file.startswith("bb/") else "网"
        print(f"\n[{subj} {yr} #{num} {qtype} · {src}]")
        print(stem[:200] + ("..." if len(stem) > 200 else ""))
        if options:
            for key in sorted(options):
                print(f"  {key}. {options[key]}")
        if answer:
            print(f"  答案: {answer[:120]}{'...' if len(answer) > 120 else ''}")


def stats() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.name, p.year, COUNT(q.id),
                   COUNT(q.answer) FILTER (WHERE q.answer IS NOT NULL)
            FROM exam_papers p
            JOIN subjects s ON s.id = p.subject_id
            LEFT JOIN questions q ON q.exam_paper_id = p.id
            GROUP BY s.name, p.year
            ORDER BY s.name, p.year
            """
        )
        rows = cur.fetchall()

    print("题库统计（题数 / 含答案）:")
    for subj, yr, total, answered in rows:
        print(f"  {subj} {yr}: {total} / {answered}")


def main() -> None:
    parser = argparse.ArgumentParser(description="查询 PostgreSQL 真题库")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="按关键词搜索题干")
    s.add_argument("keyword")
    s.add_argument("--subject", choices=["政治", "民法"])
    s.add_argument("--year", type=int)
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--source", choices=["web", "bb"], help="题目来源：网上下载 / bb 截图")

    sub.add_parser("stats", help="显示统计")

    args = parser.parse_args()
    if args.cmd == "search":
        search(args.keyword, args.subject, args.year, args.limit, args.source)
    elif args.cmd == "stats":
        stats()


if __name__ == "__main__":
    main()
