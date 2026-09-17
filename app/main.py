"""专升本真题随机出题 Web 服务。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from .llm import (  # noqa: E402
    LlmApiError,
    LlmNotConfiguredError,
    analyze_question,
    deepseek_config,
    summarize_session,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from db.connection import connect, init_schema  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"
ROOT_PATH = os.environ.get("ROOT_PATH", "").rstrip("/")


def load_env() -> None:
    if load_dotenv is None:
        return
    for path in (ROOT / ".env", ROOT / ".env.local", ROOT / ".env.production"):
        if path.exists():
            load_dotenv(path)


load_env()

app = FastAPI(
    title="专升本真题练习",
    version="1.0.0",
)


@app.on_event("startup")
def startup() -> None:
    with connect() as conn:
        init_schema(conn)


SOURCE_QUERY_PATTERN = "^(bb|web|pay)$"


def classify_source(source_file: str) -> str:
    if source_file.startswith("pay/"):
        return "pay"
    if source_file.startswith("bb/"):
        return "bb"
    return "web"


def source_label(source_file: str) -> str:
    if "河南成考网" in source_file:
        return "河南成考网"
    if source_file.startswith("pay/"):
        return "爱真题付费版"
    if source_file.startswith("bb/"):
        return "bb 截图"
    return "网上下载"


def stats_source_label(source: str) -> str:
    return {"bb": "bb 截图", "pay": "付费/抓取", "web": "网上下载"}.get(source, source)


def source_filter_clause(source: str | None) -> tuple[str, list[Any]]:
    if source == "bb":
        return " AND p.source_file LIKE 'bb/' || '%%'", []
    if source == "pay":
        return " AND p.source_file LIKE 'pay/' || '%%'", []
    if source == "web":
        return " AND p.source_file NOT LIKE 'bb/' || '%%' AND p.source_file NOT LIKE 'pay/' || '%%'", []
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
        "source": classify_source(source_file),
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
    source: str | None = Query(None, pattern=SOURCE_QUERY_PATTERN),
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
    source: str | None = Query(None, pattern=SOURCE_QUERY_PATTERN),
) -> list[dict[str, Any]]:
    sql = """
        SELECT s.name, p.year,
               CASE
                   WHEN p.source_file LIKE 'bb/' || '%%' THEN 'bb'
                   WHEN p.source_file LIKE 'pay/' || '%%' THEN 'pay'
                   ELSE 'web'
               END AS source,
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
            "source_label": stats_source_label(src),
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
    source: str | None = Query(None, pattern=SOURCE_QUERY_PATTERN),
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
        elif source == "pay":
            detail = "没有符合条件的付费/抓取题"
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
    source: str | None = Query(None, pattern=SOURCE_QUERY_PATTERN),
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


def fetch_question(question_id: int) -> dict[str, Any]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT q.id, s.name, p.year, q.number, q.question_type::text,
                   q.section_title, q.stem, q.options, q.answer, q.explanation,
                   p.source_file
            FROM questions q
            JOIN exam_papers p ON p.id = q.exam_paper_id
            JOIN subjects s ON s.id = p.subject_id
            WHERE q.id = %s
            """,
            (question_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="题目不存在")
    return row_to_question(row)


@app.get("/api/ai/status")
def ai_status() -> dict[str, Any]:
    cfg = deepseek_config()
    return {
        "available": cfg is not None,
        "model": cfg[2] if cfg else None,
    }


@app.post("/api/questions/{question_id}/analyze")
def analyze_question_api(question_id: int) -> dict[str, Any]:
    question = fetch_question(question_id)
    try:
        return analyze_question(question)
    except LlmNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LlmApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class SessionSummaryRequest(BaseModel):
    total: int = Field(ge=0)
    choice_answered: int = Field(ge=0)
    choice_correct: int = Field(ge=0)
    choice_wrong: int = Field(ge=0)
    accuracy: int | None = None
    subjective_total: int = Field(ge=0)
    subjective_viewed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    deepseek_checked: int = Field(ge=0)
    deepseek_disagree: int = Field(ge=0)
    avg_similarity: int | None = None
    duration_seconds: int = Field(ge=0)


@app.post("/api/session/summary")
def session_summary_api(body: SessionSummaryRequest) -> dict[str, Any]:
    try:
        return summarize_session(body.model_dump())
    except LlmNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LlmApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/")
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    base_href = f"{ROOT_PATH}/" if ROOT_PATH else "/"
    base_tag = f'  <base href="{base_href}" />\n'
    html = html.replace("<head>\n", f"<head>\n{base_tag}", 1)
    static_version = str(int(max(
        (STATIC_DIR / "app.js").stat().st_mtime,
        (STATIC_DIR / "style.css").stat().st_mtime,
    )))
    html = html.replace("static/style.css", f"static/style.css?v={static_version}", 1)
    html = html.replace("static/app.js", f"static/app.js?v={static_version}", 1)
    return HTMLResponse(html)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
