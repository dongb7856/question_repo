#!/usr/bin/env python3
"""将 questions/ 目录下的 .txt 真题导入 PostgreSQL。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from db.connection import connect, init_schema  # noqa: E402
from parse_ocr import discover_bb_year_files, parse_bb_year_file  # noqa: E402
from parse_questions import ParsedPaper, discover_txt_files, parse_file  # noqa: E402

QUESTIONS_DIR = ROOT / "questions"


def upsert_subject(cur, name: str) -> int:
    cur.execute(
        """
        INSERT INTO subjects (name) VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (name,),
    )
    return cur.fetchone()[0]


def upsert_exam_paper(cur, paper: ParsedPaper, subject_id: int, source_kind: str) -> int:
    cur.execute(
        """
        INSERT INTO exam_papers (
            subject_id, year, title, source_file, source_kind, notes
        ) VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (subject_id, year, source_file) DO UPDATE SET
            title = EXCLUDED.title,
            notes = EXCLUDED.notes,
            source_kind = EXCLUDED.source_kind
        RETURNING id
        """,
        (
            subject_id,
            paper.year,
            paper.title,
            paper.source_file,
            source_kind,
            paper.notes,
        ),
    )
    paper_id = cur.fetchone()[0]

    cur.execute("DELETE FROM questions WHERE exam_paper_id = %s", (paper_id,))
    return paper_id


def insert_questions(cur, paper_id: int, paper: ParsedPaper) -> int:
    count = 0
    for q in paper.questions:
        cur.execute(
            """
            INSERT INTO questions (
                exam_paper_id, number, question_type, section_title,
                stem, options, answer, explanation, raw_text
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                paper_id,
                q.number,
                q.question_type.value,
                q.section_title,
                q.stem,
                None if q.options is None else json.dumps(q.options, ensure_ascii=False),
                q.answer,
                q.explanation,
                q.raw_text,
            ),
        )
        count += 1
    return count


def import_paper(cur, paper: ParsedPaper, source_kind: str) -> int:
    subject_id = upsert_subject(cur, paper.subject)
    paper_id = upsert_exam_paper(cur, paper, subject_id, source_kind)
    return insert_questions(cur, paper_id, paper)


def import_all(reset: bool = False, bb_only: bool = False) -> None:
    txt_files = [] if bb_only else discover_txt_files(QUESTIONS_DIR)
    bb_files = discover_bb_year_files(QUESTIONS_DIR)

    if not txt_files and not bb_files:
        print("未找到可导入文件")
        return

    with connect() as conn:
        init_schema(conn)

        if reset:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE questions, exam_papers, subjects RESTART IDENTITY CASCADE")
            conn.commit()
            print("已清空旧数据")

        total_questions = 0
        total_papers = 0

        with conn.cursor() as cur:
            if txt_files:
                print("导入 txt 真题...")
                for path in txt_files:
                    paper = parse_file(path)
                    n = import_paper(cur, paper, source_kind="txt")
                    total_questions += n
                    total_papers += 1
                    status = f"{n} 题" if n else (paper.notes or "0 题")
                    print(f"  {paper.subject}/{paper.year}/{paper.source_file}: {status}")

            if bb_files:
                print("\n导入 bb OCR 真题...")
                for path in bb_files:
                    paper = parse_bb_year_file(path, QUESTIONS_DIR)
                    n = import_paper(cur, paper, source_kind="ocr")
                    total_questions += n
                    total_papers += 1
                    answered = sum(1 for q in paper.questions if q.answer)
                    status = f"{n} 题（{answered} 含答案）"
                    print(f"  {paper.subject}/{paper.year}/{paper.source_file}: {status}")

        conn.commit()

    print(f"\n完成: {total_papers} 套试卷, {total_questions} 道题")
    print_summary()


def print_summary() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.name, p.year, COUNT(q.id) AS cnt
            FROM exam_papers p
            JOIN subjects s ON s.id = p.subject_id
            LEFT JOIN questions q ON q.exam_paper_id = p.id
            GROUP BY s.name, p.year
            ORDER BY s.name, p.year
            """
        )
        rows = cur.fetchall()
        print("\n汇总:")
        for subject, year, cnt in rows:
            print(f"  {subject} {year}: {cnt} 题")


def main() -> None:
    parser = argparse.ArgumentParser(description="导入真题到 PostgreSQL")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="清空后重新导入",
    )
    parser.add_argument(
        "--bb-only",
        action="store_true",
        help="仅导入 bb 截图 OCR 结果",
    )
    args = parser.parse_args()
    import_all(reset=args.reset, bb_only=args.bb_only)


if __name__ == "__main__":
    main()
