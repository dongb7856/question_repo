#!/usr/bin/env python3
"""将 questions/pay/ 下的 .doc / .pdf 转为 .txt（doc 用 macOS textutil，pdf 用 pypdf）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PAY_DIR = Path(__file__).resolve().parents[1] / "questions" / "pay"


def convert_doc(path: Path) -> Path:
    out = path.with_suffix(".txt")
    proc = subprocess.run(
        ["textutil", "-convert", "txt", "-output", str(out), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"转换失败: {path.name}\n{proc.stderr}")
    return out


def convert_pdf(path: Path) -> Path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from parse_pay import extract_pdf

    out = path.with_suffix(".txt")
    text = extract_pdf(path)
    out.write_text(text, encoding="utf-8")
    return out


def main() -> None:
    pdfs = sorted(PAY_DIR.rglob("*.pdf"))
    for pdf in pdfs:
        out = convert_pdf(pdf)
        print(f"  {pdf.name} -> {out.name}")

    if sys.platform != "darwin" or not __import__("shutil").which("textutil"):
        if pdfs:
            print(f"\n完成: {len(pdfs)} 个 PDF 已转为 .txt")
        else:
            print("未找到 .doc / .pdf 文件")
        if sys.platform != "darwin":
            print("（非 macOS，已跳过 .doc 转换）")
        return

    docs = sorted(PAY_DIR.rglob("*.doc"))
    if not docs and not pdfs:
        print("未找到 .doc / .pdf 文件")
        return

    for doc in docs:
        out = convert_doc(doc)
        print(f"  {doc.name} -> {out.name}")

    print(f"\n完成: {len(docs)} 个 doc, {len(pdfs)} 个 pdf 已转为 .txt")
    print("确认解析无误后可删除原 .doc / .pdf 文件")


if __name__ == "__main__":
    main()
