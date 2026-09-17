"""解析 questions/pay/ 爱真题付费版（.txt / .pdf）。"""

from __future__ import annotations

import re
from pathlib import Path

from parse_questions import (
    ParsedPaper,
    ParsedQuestion,
    QuestionType,
    parse_text_content,
)

PAY_DIR = Path(__file__).resolve().parents[1] / "questions" / "pay"

# PDF 答案段缺失时的人工补全（题号来自公开参考答案）
PAY_ANSWER_FALLBACKS: dict[tuple[str, int, int], str] = {
    ("政治", 2023, 26): "D",
}

ANSWER_SECTION_SPLIT = re.compile(
    r"(?:^|\n)(?:答案解析|参考答案|^答案[:：]\s*$|第Ⅰ卷\(选择题\)\s*\n答案[:：])",
    re.M,
)
CHOICE_ANSWER_LINE = re.compile(r"^(\d+)[、.．]\s*([A-D])\s*$")
COMPACT_ANSWER_TOKENS = re.compile(r"(\d+)[、.．]\s*([A-H])")
SUBJECTIVE_ANSWER_LINE = re.compile(r"^(\d+)[、.．]\s*(.+)$")
INCOMPLETE_OPTION_TAIL = re.compile(r"\s+[A-D][\.．]\s*$")
QUESTION_LINE = re.compile(r"^\d+[、.．]")
OPTION_LINE = re.compile(r"^[A-D][\.．]")


def extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8")
    raise ValueError(f"不支持的文件类型: {path}，请使用 .txt 或 .pdf")


def infer_subject(path: Path) -> str:
    if path.parent.name in ("政治", "民法", "英语"):
        return path.parent.name
    if "政治" in path.name:
        return "政治"
    if "民法" in path.name:
        return "民法"
    if "英语" in path.name:
        return "英语"
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


def _has_inline_options(line: str) -> bool:
    return len(re.findall(r"[A-D][\.．]\s*\S", line)) >= 2


def _is_pay_section_title(line: str) -> bool:
    cleaned = line.strip()
    if not cleaned or len(cleaned) > 24:
        return False
    markers = (
        "语音题",
        "日常对话题",
        "词汇和语法",
        "阅读理解",
        "完形填空",
        "作文",
        "Phonetics",
        "Writing",
        "Cloze",
        "Dialogue",
    )
    return any(m in cleaned for m in markers)


def _should_join_pay_line(cur: str, nxt: str) -> bool:
    if re.search(r"【正确答案】", cur):
        return False
    if QUESTION_LINE.match(nxt) or _is_pay_section_title(nxt):
        return False
    if INCOMPLETE_OPTION_TAIL.search(cur):
        return True
    if re.search(r"[A-D][\.．]", cur) and nxt and nxt[0].islower():
        return True
    if QUESTION_LINE.match(cur) and not _has_inline_options(cur):
        if not QUESTION_LINE.match(nxt) and not OPTION_LINE.match(nxt):
            return True
    if "______" in cur and not QUESTION_LINE.match(nxt) and not OPTION_LINE.match(nxt):
        return True
    return False


def join_wrapped_exam_lines(text: str) -> str:
    """合并 PDF 提取后折行的题干/选项（英语 2023/2024 等）。"""
    lines = text.splitlines()
    out: list[str] = []
    buf: str | None = None

    for raw in lines:
        line = raw.strip()
        if not line:
            if buf is not None:
                out.append(buf)
                buf = None
            out.append("")
            continue

        if buf is None:
            buf = line
            continue

        if _should_join_pay_line(buf, line):
            buf = f"{buf} {line}"
        else:
            out.append(buf)
            buf = line

    if buf is not None:
        out.append(buf)
    return "\n".join(out)


def normalize_pay_exam_text(text: str, subject: str, year: int) -> str:
    # 仅 PDF 转 txt 的近年英语卷需要折行合并；doc 来源的旧卷合并会弄乱格式
    if subject == "英语" and year >= 2023:
        return join_wrapped_exam_lines(text)
    return text


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

        if COMPACT_ANSWER_TOKENS.search(line) and not CHOICE_ANSWER_LINE.match(line):
            flush()
            for m in COMPACT_ANSWER_TOKENS.finditer(line):
                num = int(m.group(1))
                results[num] = {"answer": m.group(2), "explanation": None}
            current = None
            expl_parts = []
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


def apply_answer_fallbacks(
    subject: str, year: int, questions: list[ParsedQuestion]
) -> None:
    for q in questions:
        if q.answer:
            continue
        fallback = PAY_ANSWER_FALLBACKS.get((subject, year, q.number))
        if fallback:
            q.answer = fallback


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
        if path.suffix.lower() not in {".pdf", ".txt"}:
            continue
        subject = infer_subject(path)
        year = infer_year(path)
        key = (subject, year)
        score = 0
        if "答案解析" in path.name or "答案" in path.name:
            score += 2
        if path.suffix.lower() == ".txt":
            score += 2
        elif path.suffix.lower() == ".pdf":
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
    if path.suffix.lower() == ".txt":
        score += 2
    elif path.suffix.lower() == ".pdf":
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
    exam_text = normalize_pay_exam_text(exam_text, subject, year)
    questions = parse_text_content(
        exam_text if answer_text else normalize_pay_exam_text(text, subject, year)
    )

    if answer_text:
        merge_answers(questions, parse_answer_section(answer_text))

    apply_answer_fallbacks(subject, year, questions)

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
