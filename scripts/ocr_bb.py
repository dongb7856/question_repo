#!/usr/bin/env python3
"""对 questions/*/bb/ 下的截图做 OCR，并按年份拆分保存。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "questions"

YEAR_HEADER = re.compile(
    r"(20[12]\d)年成人.*?全国统一.*?专升本(政治|民法)",
    re.I,
)


def natural_key(path: Path) -> int:
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else 0


def ocr_image(ocr: RapidOCR, path: Path, max_dim: int = 2400) -> list[str]:
    img = Image.open(path)
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)))
    arr = np.array(img.convert("RGB"))
    result, _ = ocr(arr)
    return [item[1] for item in (result or [])]


def ocr_folder(folder: Path, max_dim: int) -> str:
    ocr = RapidOCR()
    chunks: list[str] = []
    images = sorted(
        [p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}],
        key=natural_key,
    )
    for image in images:
        chunks.append(f"===== {image.name} =====")
        chunks.extend(ocr_image(ocr, image, max_dim=max_dim))
        chunks.append("")
    return "\n".join(chunks)


def split_by_year(text: str) -> dict[int, str]:
    matches = list(YEAR_HEADER.finditer(text))
    if not matches:
        return {}

    sections: dict[int, list[str]] = {}
    for idx, match in enumerate(matches):
        year = int(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.setdefault(year, []).append(text[start:end].strip())

    return {year: "\n\n".join(parts) for year, parts in sections.items()}


def process_subject(subject: str, max_dim: int, force: bool) -> None:
    folder = QUESTIONS / subject / "bb"
    if not folder.is_dir():
        print(f"跳过 {subject}: 无 bb 目录")
        return

    images = [p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
    if not images:
        print(f"跳过 {subject}: bb 目录无图片")
        return

    combined_path = folder / f"{subject}_bb_ocr.txt"
    if force or not combined_path.exists():
        print(f"OCR {subject}: {len(images)} 张图片...")
        combined = ocr_folder(folder, max_dim=max_dim)
        combined_path.write_text(combined, encoding="utf-8")
    else:
        combined = combined_path.read_text(encoding="utf-8")
        print(f"复用已有 OCR: {combined_path}")

    sections = split_by_year(combined)
    if not sections:
        print(f"  警告: {subject} 未识别到年份标题")
        return

    for year, section in sorted(sections.items()):
        year_path = folder / f"{year}.txt"
        year_path.write_text(section, encoding="utf-8")
        print(f"  {subject} {year}: {len(section):,} 字符 -> {year_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR bb 截图并按年份拆分")
    parser.add_argument("--subject", choices=["政治", "民法"])
    parser.add_argument("--force", action="store_true", help="重新 OCR")
    parser.add_argument("--max-dim", type=int, default=2400)
    args = parser.parse_args()

    subjects = [args.subject] if args.subject else ["政治", "民法"]
    for subject in subjects:
        process_subject(subject, max_dim=args.max_dim, force=args.force)


if __name__ == "__main__":
    main()
