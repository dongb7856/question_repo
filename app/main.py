"""专升本真题随机出题 Web 服务。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from db.connection import connect, init_schema  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
ROOT_PATH = os.environ.get("ROOT_PATH", "").rstrip("/")

app = FastAPI(
    title="专升本真题练习",
    version="1.0.0",
    root_path=ROOT_PATH,
)


@app.on_event("startup")
def startup() -> None:
    with connect() as conn:
        init_schema(conn)


def source_label(source_file: str) -> str:
    return "bb 截图" if source_file.startswith("bb/") else "网上下载"


def source_filter_clause(source: str | None) -> tuple[str, list[Any]]:
    if source == "bb":
        return " AND p.source_file LIKE 'bb/' || '%%'", []
    if source == "web":
        return " AND p.source_file NOT LIKE 'bb/' || '%%'", []
    return "", []


def row_to_question(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        qid,
        subject,
        year,
        number,
        qtype,
        section,
        stem,
        options,
        answer,
        explanation,
        source_file,
    ) = row
    return {
        "id": qid,
        "subject": subject,
        "year": year,
        "number": number,
        "question_type": qtype,
        "section_title": section,
        "stem": stem,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "source_file": source_file,
        "source": "bb" if source_file.startswith("bb/") else "web",
        "source_label": source_label(source_file),
    }


@app.get("/api/subjects")
def list_subjects() -> list[str]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM subjects ORDER BY name")
        return [row[0] for row in cur.fetchall()]


@app.get("/api/years")
def list_years(
    subject: str | None = None,
    source: str | None = Query(None, pattern="^(bb|web)$"),
) -> list[int]:
    sql = """
        SELECT DISTINCT p.year
        FROM exam_papers p
        JOIN subjects s ON s.id = p.subject_id
        JOIN questions q ON q.exam_paper_id = p.id
        WHERE p.year > 0
    """
    params: list[Any] = []
    if subject:
        sql += " AND s.name = %s"
        params.append(subject)
    source_sql, source_params = source_filter_clause(source)
    sql += source_sql
    params.extend(source_params)
    sql += " ORDER BY p.year DESC"

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return [row[0] for row in cur.fetchall()]


@app.get("/api/stats")
def stats(
    source: str | None = Query(None, pattern="^(bb|web)$"),
) -> list[dict[str, Any]]:
    sql = """
        SELECT s.name, p.year,
               CASE WHEN p.source_file LIKE 'bb/' || '%%' THEN 'bb' ELSE 'web' END AS source,
               COUNT(q.id),
               COUNT(q.answer) FILTER (WHERE q.answer IS NOT NULL)
        FROM exam_papers p
        JOIN subjects s ON s.id = p.subject_id
        LEFT JOIN questions q ON q.exam_paper_id = p.id
        WHERE p.year > 0
    """
    params: list[Any] = []
    source_sql, source_params = source_filter_clause(source)
    sql += source_sql
    params.extend(source_params)
    sql += """
        GROUP BY s.name, p.year, source
        HAVING COUNT(q.id) > 0
        ORDER BY s.name, p.year DESC, source
    """

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "subject": subject,
            "year": year,
            "source": src,
            "source_label": "bb 截图" if src == "bb" else "网上下载",
            "total": total,
            "answered": answered,
            "from_bb": src == "bb",
        }
        for subject, year, src, total, answered in rows
    ]


@app.get("/api/questions/random")
def random_questions(
    count: int = Query(10, ge=1, le=50),
    subject: str | None = None,
    year: int | None = None,
    question_type: str | None = None,
    source: str | None = Query(None, pattern="^(bb|web)$"),
) -> list[dict[str, Any]]:
    sql = """
        SELECT q.id, s.name, p.year, q.number, q.question_type::text,
               q.section_title, q.stem, q.options, q.answer, q.explanation,
               p.source_file
        FROM questions q
        JOIN exam_papers p ON p.id = q.exam_paper_id
        JOIN subjects s ON s.id = p.subject_id
        WHERE p.year > 0
    """
    params: list[Any] = []

    if subject:
        sql += " AND s.name = %s"
        params.append(subject)
    if year:
        sql += " AND p.year = %s"
        params.append(year)
    if question_type:
        sql += " AND q.question_type::text = %s"
        params.append(question_type)
    source_sql, source_params = source_filter_clause(source)
    sql += source_sql
    params.extend(source_params)

    sql += " ORDER BY random() LIMIT %s"
    params.append(count)

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    if not rows:
        detail = "没有符合条件的题目"
        if source == "bb":
            detail = "没有符合条件的 bb 截图题"
        elif source == "web":
            detail = "没有符合条件的网上下载题"
        raise HTTPException(status_code=404, detail=detail)
    return [row_to_question(row) for row in rows]


@app.get("/api/questions/search")
def search_questions(
    keyword: str = Query(..., min_length=1),
    subject: str | None = None,
    year: int | None = None,
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(None, pattern="^(bb|web)$"),
) -> list[dict[str, Any]]:
    sql = """
        SELECT q.id, s.name, p.year, q.number, q.question_type::text,
               q.section_title, q.stem, q.options, q.answer, q.explanation,
               p.source_file
        FROM questions q
        JOIN exam_papers p ON p.id = q.exam_paper_id
        JOIN subjects s ON s.id = p.subject_id
        WHERE q.stem ILIKE %s
    """
    params: list[Any] = [f"%{keyword}%"]

    if subject:
        sql += " AND s.name = %s"
        params.append(subject)
    if year:
        sql += " AND p.year = %s"
        params.append(year)
    source_sql, source_params = source_filter_clause(source)
    sql += source_sql
    params.extend(source_params)

    sql += " ORDER BY s.name, p.year DESC, q.number LIMIT %s"
    params.append(limit)

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [row_to_question(row) for row in rows]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
