#!/usr/bin/env python3
"""搜索并采集 2020-2025 成人高考专升本政治/民法高质量真题，写入 questions/high_quality/。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.download_questions import (  # noqa: E402
    extract_aipta,
    extract_generic,
    fetch,
    html_to_text,
)
from scripts.parse_questions import ParsedPaper, QuestionType, parse_text_content  # noqa: E402

QUESTIONS = ROOT / "questions"
HIGH_QUALITY = QUESTIONS / "high_quality"
SOURCES = QUESTIONS / "sources"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

SUBJECTS = ("政治", "民法")
YEARS = tuple(range(2020, 2026))


@dataclass
class SourceSpec:
    source_id: str
    subject: str
    year: int
    url: str
    kind: str  # html_aipta | html | pdf
    filename: str
    note: str = ""


# 经网络检索筛选：爱真题网页版选项清晰；环球网校 PDF 含答案（回忆版）
SOURCE_CATALOG: list[SourceSpec] = [
    # 政治
    SourceSpec("aipta", "政治", 2020, "https://www.aipta.com/article/586.html", "html_aipta", "586.html"),
    SourceSpec("hqwx", "政治", 2020, "https://oss-hqwx-video.hqwx.com/2020年成人高考专升本政治考试真题及答案解析_c7dd1fb85aeb326a965e365d317f809478c0ab2f.pdf", "pdf", "2020政治.pdf"),
    SourceSpec("ah_edu", "政治", 2021, "http://www.ah-edu.com/beikao/10271.html", "html_ah_edu", "10271.html", "安徽成考网完整回忆版"),
    SourceSpec("hqwx", "政治", 2021, "https://oss-hqwx-video.hqwx.com/2021年成人高考专升本《政治》真题答案_2dfbeac9825f84957261e0f90984d0b3468cc362.pdf", "pdf", "2021政治.pdf", "仅答案要点"),
    SourceSpec("aipta", "政治", 2022, "https://www.aipta.com/article/6435.html", "html_aipta", "6435.html"),
    SourceSpec("hqwx", "政治", 2022, "https://oss-hqwx-video.hqwx.com/2022年成人高考（专升本）政治真题答案（考生回忆版）_e3ff0fa5a454d8b4becff2c7cfd95bc98c122bef.pdf", "pdf", "2022政治答案.pdf"),
    SourceSpec("aipta", "政治", 2023, "https://www.aipta.com/article/9369.html", "html_aipta", "9369.html"),
    SourceSpec("hqwx", "政治", 2023, "https://oss-hqwx-video.hqwx.com/2023年成人高考（专升本）政治真题答案（考生回忆版）_8323dd113e17667a07c3483e84acdc1158e1f715.pdf", "pdf", "2023政治答案.pdf"),
    SourceSpec("hbcj", "政治", 2024, "https://hbcj1.com/xiangqing?article_id=874", "html_hbcj", "874.html", "含括号标注的选择题答案"),
    SourceSpec("aipta", "政治", 2024, "https://www.aipta.com/article/10317.html", "html_aipta_combo", "10317.html", "汇总页仅展示部分选择题"),
    SourceSpec("hqwx", "政治", 2024, "https://oss-hqwx-video.hqwx.com/2024年成人高考专升本政治真题答案（10.20更新版）_247bb73ce0597ea6c900bdae678347704891fe57.pdf", "pdf", "2024政治.pdf"),
    SourceSpec("hqwx", "政治", 2025, "https://oss-hqwx-video.hqwx.com/免费-2025年成考专升本政治真题及答案解析_2877f4d0681cfe162eb7d5632337f6920e4dd172.pdf", "pdf", "2025政治.pdf"),
    # 民法
    SourceSpec("aipta", "民法", 2020, "https://www.aipta.com/article/604.html", "html_aipta", "604.html"),
    SourceSpec("aipta", "民法", 2021, "https://www.aipta.com/article/603.html", "html_aipta", "603.html"),
    SourceSpec("aipta", "民法", 2022, "https://www.aipta.com/article/8979.html", "html_aipta", "8979.html"),
    SourceSpec("hqwx", "民法", 2022, "https://oss-hqwx-video.hqwx.com/2022年成人高考（专升本）民法真题答案（考生回忆版）_e93b3b44127e3262510c84a20dad5ee294c64ec3.pdf", "pdf", "2022民法答案.pdf"),
    SourceSpec("aipta", "民法", 2023, "https://www.aipta.com/article/8980.html", "html_aipta", "8980.html"),
    SourceSpec("aipta", "民法", 2024, "https://www.aipta.com/article/10129.html", "html_aipta", "10129.html"),
    SourceSpec(
        "gdck84",
        "民法",
        2025,
        "https://www.gdck84.com/show-24-21655-1.html",
        "html_gdck84",
        "21655.html",
        "PNG 截图，需 OCR",
    ),
]

def extract_aipta_combo(html: str, subject: str, year: int) -> str:
    """从爱真题多年份汇总页提取指定年份正文。"""
    m = re.search(r'<div class="info-bodygg">([\s\S]*?)</div>', html)
    chunk = m.group(1) if m else html
    text = html_to_text(chunk)
    marker = f"{year}成人高考"
    idx = text.find(marker)
    if idx == -1:
        return text
    part = text[idx:]
    nxt = re.search(r"\n20\d\d成人高考", part[10:])
    if nxt:
        part = part[: nxt.start() + 10]
    return part.strip()


def extract_ah_edu(html: str) -> str:
    m = re.search(r"一、选择题：1-35小题[\s\S]*", html)
    if not m:
        return extract_generic(html)
    chunk = m.group(0)
    end = re.search(r"相关推荐|上一篇|下一篇|版权", chunk)
    if end:
        chunk = chunk[: end.start()]
    return html_to_text(chunk)


def extract_hbcj(html: str) -> str:
    m = re.search(r'<div class="content[^"]*">([\s\S]*?)</div>\s*<div class="', html)
    if not m:
        m = re.search(r"一、单项选择题[\s\S]*", html)
        return html_to_text(m.group(0) if m else html)
    return html_to_text(m.group(1))


def extract_gdck84(html: str, dest_dir: Path) -> str:
    m = re.search(r'<div class="content table">([\s\S]*?)</div>', html)
    chunk = m.group(1) if m else html
    lines: list[str] = []
    for img_m in re.finditer(r'<img[^>]+src="([^"]+)"', chunk):
        url = img_m.group(1)
        if "uploadfile" not in url:
            continue
        name = Path(url.split("?")[0]).name
        img_path = dest_dir / name
        if not img_path.exists():
            img_path.write_bytes(fetch(url))
        lines.append(f"===== {name} =====")
        lines.append(f"[图片] {url}")
    intro = html_to_text(re.sub(r"<img[^>]+>", "", chunk))
    if intro.strip():
        lines.insert(0, intro.strip())
    return "\n\n".join(lines).strip()


def extract_html_text(html: str, kind: str, subject: str, year: int, dest_dir: Path) -> str:
    if kind == "html_aipta":
        return extract_aipta(html)
    if kind == "html_aipta_combo":
        return extract_aipta_combo(html, subject, year)
    if kind == "html_ah_edu":
        return extract_ah_edu(html)
    if kind == "html_hbcj":
        return extract_hbcj(html)
    if kind == "html_gdck84":
        return extract_gdck84(html, dest_dir)
    return extract_generic(html)


def extract_pdf_text(data: bytes) -> str:
    dest = Path("/tmp/question_repo_pdf_extract.pdf")
    dest.write_bytes(data)
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(dest))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return ""


def normalize_for_parse(text: str) -> str:
    """统一常见排版差异，提升选项/答案识别率。"""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"^(\d+)[、.．]\s*单选题\s*$", r"\1、", text, flags=re.M)
    # PDF: 1.题干(A) -> 保留括号答案
    text = re.sub(r"^(\d+)\.([^\n]+)$", r"\1、\2", text, flags=re.M)
    return text.strip()


def score_paper(paper: ParsedPaper) -> dict:
    choices = [q for q in paper.questions if q.question_type == QuestionType.CHOICE]
    with_options = [q for q in choices if q.options and len(q.options) >= 2]
    full_options = [q for q in choices if q.options and len(q.options) >= 4]
    with_answer = [q for q in paper.questions if q.answer]

    # 优先四选项完整度，其次答案覆盖率
    choice_score = len(full_options) * 10 + len(with_options) * 3
    answer_score = len(with_answer) * 4
    total_score = choice_score + answer_score + len(paper.questions)

    return {
        "total_questions": len(paper.questions),
        "choice_count": len(choices),
        "with_4_options": len(full_options),
        "with_answer": len(with_answer),
        "score": total_score,
    }


def download_source(spec: SourceSpec) -> tuple[Path, str]:
    dest_dir = SOURCES / spec.source_id / spec.subject / str(spec.year)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / spec.filename

    if dest.exists() and dest.stat().st_size > 0:
        raw = dest.read_bytes()
    else:
        print(f"  下载 {spec.source_id}/{spec.subject}/{spec.year} ...")
        raw = fetch(spec.url)
        dest.write_bytes(raw)

    if spec.kind == "pdf":
        text = normalize_for_parse(extract_pdf_text(raw))
        txt_path = dest_dir / (dest.stem + ".txt")
        txt_path.write_text(text, encoding="utf-8")
        return txt_path, text

    html = raw.decode("utf-8", errors="replace")
    text = normalize_for_parse(
        extract_html_text(html, spec.kind, spec.subject, spec.year, dest_dir)
    )
    txt_path = dest_dir / (dest.stem + ".txt")
    txt_path.write_text(text, encoding="utf-8")
    return txt_path, text


def pick_best_source(subject: str, year: int) -> tuple[SourceSpec | None, ParsedPaper | None, dict]:
    specs = [s for s in SOURCE_CATALOG if s.subject == subject and s.year == year]
    best_spec: SourceSpec | None = None
    best_paper: ParsedPaper | None = None
    best_metrics: dict = {"score": -1}

    for spec in specs:
        try:
            txt_path, text = download_source(spec)
            if len(text.strip()) < 100:
                continue
            paper = ParsedPaper(
                subject=subject,
                year=year,
                source_file=str(txt_path.relative_to(QUESTIONS)),
                title=f"{subject} {year}",
                questions=parse_text_content(text),
            )
            metrics = score_paper(paper)
            metrics["source_id"] = spec.source_id
            metrics["source_url"] = spec.url
            metrics["source_file"] = spec.filename
            metrics["note"] = spec.note
            if metrics["score"] > best_metrics["score"]:
                best_spec, best_paper, best_metrics = spec, paper, metrics
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {spec.source_id} 失败: {exc}")

    return best_spec, best_paper, best_metrics


def write_high_quality(subject: str, year: int, text: str, meta: dict) -> None:
    dest_dir = HIGH_QUALITY / subject / str(year)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 2025 民法：同步 PNG 截图到 high_quality 便于 OCR
    if subject == "民法" and year == 2025:
        src_img_dir = SOURCES / "gdck84" / "民法" / "2025"
        if src_img_dir.is_dir():
            img_dest = dest_dir / "images"
            img_dest.mkdir(exist_ok=True)
            meta["image_files"] = []
            for png in sorted(src_img_dir.glob("*.png")):
                target = img_dest / png.name
                if not target.exists():
                    target.write_bytes(png.read_bytes())
                meta["image_files"].append(f"images/{png.name}")

    (dest_dir / "paper.txt").write_text(text, encoding="utf-8")
    (dest_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_readme(manifest: dict) -> str:
    lines = [
        "# 高质量专升本真题库",
        "",
        "科目：**政治**、**民法**（成人高考专升本，法学类）",
        "年份：**2020–2025**",
        "",
        "> 本目录存放经自动评分筛选后的高质量真题文本，选项与答案结构清晰，可直接被 `scripts/parse_questions.py` 解析入库。",
        "",
        "## 目录结构",
        "",
        "```",
        "questions/",
        "  high_quality/          # 精选可解析文本（本目录）",
        "    政治/2020/paper.txt",
        "    政治/2020/meta.json",
        "  sources/               # 各来源原始下载与提取文本",
        "    aipta/政治/2020/",
        "    hqwx/政治/2020/",
        "  政治/2020/             # 早期 raw 下载（保留）",
        "  民法/bb/               # 截图 OCR，质量较低，仅供参考",
        "```",
        "",
        "## 来源说明",
        "",
        "| 来源 | 特点 |",
        "|------|------|",
        "| [爱真题](https://www.aipta.com/zt/crgk/zb/) | 题干 + A/B/C/D 选项排版规范，适合程序抽取 |",
        "| [环球网校](https://www.hqwx.com/chengrengk-kaoshi/ziliaolm/5993/) | PDF 回忆版，含选择题答案标注 |",
        "| [安徽成考网](http://www.ah-edu.com/beikao/10271.html) | 2021 政治完整回忆版 |",
        "| hbcj1.com | 2024 政治，题干含 (A) 答案标注 |",
        "| [广东成考网](https://www.gdck84.com/) | 2025 民法 PNG 截图 |",
        "",
        "## 各年份质量概览",
        "",
        "| 科目 | 年份 | 来源 | 题目数 | 四选项选择题 | 含答案 | 评分 | 备注 |",
        "|------|------|------|--------|--------------|--------|------|------|",
    ]

    for subject in SUBJECTS:
        for year in YEARS:
            key = f"{subject}/{year}"
            entry = manifest.get(key)
            if not entry:
                lines.append(f"| {subject} | {year} | - | - | - | - | - | 未采集 |")
                continue
            m = entry["metrics"]
            note = m.get("note") or entry.get("quality_note") or ""
            lines.append(
                f"| {subject} | {year} | {m.get('source_id', '-')} | "
                f"{m.get('total_questions', 0)} | {m.get('with_4_options', 0)} | "
                f"{m.get('with_answer', 0)} | {m.get('score', 0)} | {note} |"
            )

    lines.extend(
        [
            "",
            "## 使用",
            "",
            "- 重新采集：`python3 scripts/collect_high_quality.py`",
            "- 解析入库：`python3 scripts/import_questions.py`（可指向 high_quality 目录）",
            "",
            "## 质量分级",
            "",
            "- **A**：≥30 道四选项选择题，且 ≥10 道含答案",
            "- **B**：≥30 道四选项选择题",
            "- **C**：有部分题目，需人工校对",
            "- **D**：仅答案或 OCR 碎片，不建议直接入库",
        ]
    )
    return "\n".join(lines) + "\n"


def quality_grade(metrics: dict) -> str:
    if metrics.get("with_4_options", 0) >= 30 and metrics.get("with_answer", 0) >= 10:
        return "A"
    if metrics.get("with_4_options", 0) >= 30:
        return "B"
    if metrics.get("total_questions", 0) >= 10:
        return "C"
    return "D"


def main() -> None:
    print("=== 采集高质量专升本真题 2020-2025 ===\n")
    manifest: dict = {}

    for subject in SUBJECTS:
        for year in YEARS:
            print(f"[{subject} {year}]")
            spec, paper, metrics = pick_best_source(subject, year)
            key = f"{subject}/{year}"

            if not spec or not paper:
                print("  未找到可用来源\n")
                manifest[key] = {"status": "missing"}
                continue

            # 重新读取最佳来源文本
            txt_path, text = download_source(spec)
            grade = quality_grade(metrics)
            quality_note = {
                "A": "选项+答案完整，推荐入库",
                "B": "选项完整，主观题答案需补充",
                "C": "部分题目，建议人工校对",
                "D": "质量偏低，仅作参考",
            }[grade]

            meta = {
                "subject": subject,
                "year": year,
                "exam_type": "成人高考专升本",
                "quality_grade": grade,
                "quality_note": quality_note,
                "source_id": spec.source_id,
                "source_url": spec.url,
                "source_file": spec.filename,
                "metrics": metrics,
            }
            write_high_quality(subject, year, text, meta)
            manifest[key] = {"status": "ok", "quality_grade": grade, "metrics": metrics}
            print(
                f"  ✓ 选用 {spec.source_id} | "
                f"{metrics['total_questions']}题, "
                f"四选项{metrics['with_4_options']}, "
                f"有答案{metrics['with_answer']}, "
                f"等级{grade}\n"
            )

    manifest_path = HIGH_QUALITY / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HIGH_QUALITY / "README.md").write_text(build_readme(manifest), encoding="utf-8")

    ok = sum(1 for v in manifest.values() if v.get("status") == "ok")
    print(f"完成: {ok}/{len(SUBJECTS) * len(YEARS)} 套已写入 {HIGH_QUALITY}")


if __name__ == "__main__":
    main()
