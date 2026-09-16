"""解析 questions/pay/ 爱真题付费版（.doc / .pdf）。"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from parse_questions import (
    ParsedPaper,
    ParsedQuestion,
    QuestionType,
    parse_text_content,
)

PAY_DIR = Path(__file__).resolve().parents[1] / "questions" / "pay"

ANSWER_SECTION_SPLIT = re.compile(
    r"(?:^|\n)(?:答案解析|参考答案|^答案[:：]\s*$|第Ⅰ卷\(选择题\)\s*\n答案[:：])",
    re.M,
)
CHOICE_ANSWER_LINE = re.compile(r"^(\d+)[、.．]\s*([A-D])\s*$")
SUBJECTIVE_ANSWER_LINE = re.compile(r"^(\d+)[、.．]\s*(.+)$")


def _libreoffice_bin() -> str | None:
    for name in ("soffice", "libreoffice"):
        if shutil.which(name):
            return name
    return None


def _convert_doc_with_libreoffice(path: Path) -> str:
    office = _libreoffice_bin()
    if not office:
        return ""

    with tempfile.TemporaryDirectory() as tmp:
        outdir = Path(tmp)
        subprocess.run(
            [
                office,
                "--headless",
                "--convert-to",
                "txt",
                "--outdir",
                str(outdir),
                str(path),
            ],
            capture_output=True,
            check=False,
        )
        txt = outdir / f"{path.stem}.txt"
        if txt.exists():
            return txt.read_text(encoding="utf-8", errors="replace")
    return ""


def extract_doc(path: Path) -> str:
    if sys.platform == "darwin" and shutil.which("textutil"):
        proc = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout

    return _convert_doc_with_libreoffice(path)


def extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".doc":
        return extract_doc(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    raise ValueError(f"不支持的文件类型: {path}")


def infer_subject(path: Path) -> str:
    if path.parent.name in ("政治", "民法"):
        return path.parent.name
    if "政治" in path.name:
        return "政治"
    if "民法" in path.name:
        return "民法"
    raise ValueError(f"无法识别科目: {path}")


def infer_year(path: Path) -> int:
    m = re.search(r"(20\d{2})", path.name)
    if not m:
        raise ValueError(f"无法识别年份: {path}")
    return int(m.group(1))


def split_exam_and_answers(text: str) -> tuple[str, str]:
    m = ANSWER_SECTION_SPLIT.search(text)
    if not m:
        return text, ""
    return text[: m.start()].strip(), text[m.end() :].strip()


def parse_answer_section(text: str) -> dict[int, dict[str, str | None]]:
    """从 PDF 答案段提取题号 -> {answer, explanation}。"""
    results: dict[int, dict[str, str | None]] = {}
    current: int | None = None
    expl_parts: list[str] = []

    def flush() -> None:
        nonlocal current, expl_parts
        if current is None:
            return
        entry = results.setdefault(current, {"answer": None, "explanation": None})
        if expl_parts:
            entry["explanation"] = "\n".join(expl_parts).strip()
        current = None
        expl_parts = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("第") and "卷" in line:
            flush()
            continue
        if line.startswith("[考点]") or line.startswith("[解析]") or line.startswith("【"):
            if line.startswith("[解析]") or line.startswith("【试题解析】"):
                expl_parts.append(re.sub(r"^\[解析\]|^【试题解析】[:：]?\s*", "", line).strip())
            continue

        cm = CHOICE_ANSWER_LINE.match(line)
        if cm:
            flush()
            num = int(cm.group(1))
            results[num] = {"answer": cm.group(2), "explanation": None}
            current = num
            expl_parts = []
            continue

        sm = SUBJECTIVE_ANSWER_LINE.match(line)
        if sm and not re.match(r"^[A-D][．.、]", sm.group(2)):
            flush()
            num = int(sm.group(1))
            results[num] = {"answer": sm.group(2).strip(), "explanation": None}
            current = num
            expl_parts = []
            continue

        if current is not None:
            entry = results.setdefault(current, {"answer": None, "explanation": None})
            if entry["answer"]:
                expl_parts.append(line)
            else:
                entry["answer"] = (entry["answer"] or "") + line

    flush()
    return results


def merge_answers(questions: list[ParsedQuestion], answers: dict[int, dict[str, str | None]]) -> None:
    for q in questions:
        info = answers.get(q.number)
        if not info:
            continue
        if info.get("answer") and not q.answer:
            q.answer = info["answer"]
        if info.get("explanation") and not q.explanation:
            q.explanation = info["explanation"]


def discover_pay_files(root: Path = PAY_DIR) -> list[Path]:
    """优先「真题及答案解析」，跳过同年的纯「试卷」。"""
    chosen: dict[tuple[str, int], Path] = {}

    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".doc", ".pdf", ".txt"}:
            continue
        subject = infer_subject(path)
        year = infer_year(path)
        key = (subject, year)
        score = 0
        if "答案解析" in path.name or "答案" in path.name:
            score += 2
        if path.suffix.lower() == ".pdf":
            score += 1
        if "试卷" in path.name and "答案" not in path.name:
            score -= 2

        prev = chosen.get(key)
        if prev is None or score > chosen_score(prev):
            chosen[key] = path

    return sorted(chosen.values(), key=lambda p: (infer_subject(p), infer_year(p), p.name))


def chosen_score(path: Path) -> int:
    score = 0
    if "答案解析" in path.name or "答案" in path.name:
        score += 2
    if path.suffix.lower() == ".pdf":
        score += 1
    if "试卷" in path.name and "答案" not in path.name:
        score -= 2
    return score


def parse_pay_file(path: Path) -> ParsedPaper:
    subject = infer_subject(path)
    year = infer_year(path)
    text = extract_text(path)
    if not text.strip():
        return ParsedPaper(
            subject=subject,
            year=year,
            source_file=f"pay/{subject}/{path.name}",
            title=f"{subject} {year} 爱真题付费版",
            questions=[],
            notes="文本提取失败",
        )

    exam_text, answer_text = split_exam_and_answers(text)
    questions = parse_text_content(exam_text if answer_text else text)

    if answer_text:
        merge_answers(questions, parse_answer_section(answer_text))

    answered = sum(1 for q in questions if q.answer)
    explained = sum(1 for q in questions if q.explanation)
    source_label = "河南成考网" if "河南成考网" in path.name else "爱真题付费版"
    notes = f"{source_label}; {answered} 题含答案, {explained} 题含解析"

    return ParsedPaper(
        subject=subject,
        year=year,
        source_file=f"pay/{subject}/{path.name}",
        title=f"{subject} {year} {source_label}",
        questions=questions,
        notes=notes,
    )
