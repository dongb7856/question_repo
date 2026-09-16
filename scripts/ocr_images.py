#!/usr/bin/env python3
"""对 questions/*/bb/ 下的截图批量 OCR，输出 *_ocr.txt。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from ocr.tencent import OcrApiError, OcrNotConfiguredError, general_accurate_ocr

QUESTIONS_DIR = ROOT / "questions"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def load_env() -> None:
    if load_dotenv is None:
        return
    for path in (ROOT / ".env", ROOT / ".env.local"):
        if path.exists():
            load_dotenv(path)


def discover_bb_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("*/bb") if p.is_dir())


def discover_images(bb_dir: Path) -> list[Path]:
    return sorted(
        p for p in bb_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
    )


def ocr_folder(bb_dir: Path, *, force: bool = False) -> Path:
    subject = bb_dir.parent.name
    out_path = bb_dir / f"{subject}_bb_ocr.txt"
    if out_path.exists() and not force:
        print(f"  跳过 {out_path.name}（已存在，使用 --force 覆盖）")
        return out_path

    images = discover_images(bb_dir)
    if not images:
        print(f"  {bb_dir}: 无图片")
        return out_path

    chunks: list[str] = []
    for image in images:
        print(f"  OCR {image.name} ...")
        try:
            lines = general_accurate_ocr(image)
        except OcrNotConfiguredError:
            raise
        except OcrApiError as exc:
            print(f"    失败: {exc}")
            continue
        chunks.append(f"===== {image.name} =====")
        chunks.extend(lines)
        chunks.append("")

    out_path.write_text("\n".join(chunks).strip() + "\n", encoding="utf-8")
    print(f"  已写入 {out_path}（{len(images)} 张图）")
    return out_path


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="bb 文件夹截图 OCR")
    parser.add_argument("--subject", choices=["政治", "民法"], help="仅处理指定科目")
    parser.add_argument("--force", action="store_true", help="覆盖已有 OCR 文本")
    args = parser.parse_args()

    bb_dirs = discover_bb_dirs(QUESTIONS_DIR)
    if args.subject:
        bb_dirs = [p for p in bb_dirs if p.parent.name == args.subject]

    if not bb_dirs:
        print("未找到 bb 文件夹")
        return

    try:
        for bb_dir in bb_dirs:
            print(f"\n{bb_dir.parent.name}/bb")
            ocr_folder(bb_dir, force=args.force)
    except OcrNotConfiguredError as exc:
        print(f"\n错误: {exc}")
        print("请复制 .env.example 为 .env 并填入腾讯云 OCR 密钥。")
        sys.exit(1)


if __name__ == "__main__":
    main()
