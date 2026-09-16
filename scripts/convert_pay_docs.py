#!/usr/bin/env python3
"""将 questions/pay/ 下的 .doc 转为 .txt（macOS textutil，无需 LibreOffice）。"""

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


def main() -> None:
    if sys.platform != "darwin" or not __import__("shutil").which("textutil"):
        print("需要 macOS 且已安装 textutil", file=sys.stderr)
        sys.exit(1)

    docs = sorted(PAY_DIR.rglob("*.doc"))
    if not docs:
        print("未找到 .doc 文件")
        return

    for doc in docs:
        out = convert_doc(doc)
        print(f"  {doc.name} -> {out.name}")

    print(f"\n完成: {len(docs)} 个文件已转为 .txt")
    print("确认解析无误后可删除原 .doc 文件")


if __name__ == "__main__":
    main()
