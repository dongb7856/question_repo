#!/usr/bin/env python3
"""执行 migration 清空旧题，并从 questions/pay/ 导入爱真题付费版。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from db.connection import connect, init_schema  # noqa: E402
from db.migrate import run_migrations  # noqa: E402
from import_questions import import_paper, print_summary  # noqa: E402
from parse_pay import PAY_DIR, discover_pay_files, parse_pay_file  # noqa: E402


def import_pay() -> None:
    files = discover_pay_files(PAY_DIR)
    if not files:
        print(f"未在 {PAY_DIR} 找到可导入文件")
        return

    print(f"发现 {len(files)} 套 pay 真题\n")

    total_questions = 0
    total_papers = 0

    with connect() as conn:
        init_schema(conn)
        with conn.cursor() as cur:
            for path in files:
                try:
                    paper = parse_pay_file(path)
                except Exception as exc:
                    print(f"  SKIP {path.name}: 解析失败 ({exc})")
                    continue

                suffix = path.suffix.lower()
                kind = {
                    ".pdf": "pay_pdf",
                    ".txt": "pay_txt",
                }[suffix]
                n = import_paper(cur, paper, source_kind=kind)
                total_questions += n
                total_papers += 1
                answered = sum(1 for q in paper.questions if q.answer)
                explained = sum(1 for q in paper.questions if q.explanation)
                print(
                    f"  {paper.subject}/{paper.year}/{path.name}: "
                    f"{n} 题（答案 {answered}，解析 {explained}）"
                )
        conn.commit()

    print(f"\n完成: {total_papers} 套试卷, {total_questions} 道题")
    print_summary()


def main() -> None:
    print("=== Step 1: 执行 migration（清空旧题目）===\n")
    run_migrations()
    print("\n=== Step 2: 导入 pay/ 付费真题 ===\n")
    import_pay()


if __name__ == "__main__":
    main()
