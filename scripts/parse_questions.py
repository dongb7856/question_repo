"""从 .txt 真题文件中解析结构化题目。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class QuestionType(str, Enum):
    CHOICE = "choice"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    CASE_ANALYSIS = "case_analysis"
    OTHER = "other"


SECTION_TYPE_MAP: list[tuple[re.Pattern[str], QuestionType]] = [
    (
        re.compile(r"单项选择|选择题|词汇和语法|阅读理解|完形填空|语音题|日常对话"),
        QuestionType.CHOICE,
    ),
    (re.compile(r"问答题|辨析题"), QuestionType.SHORT_ANSWER),
    (re.compile(r"简答"), QuestionType.SHORT_ANSWER),
    (re.compile(r"论述|写作|翻译"), QuestionType.ESSAY),
    (re.compile(r"案例"), QuestionType.CASE_ANALYSIS),
]

OPTION_LINE_HINT = re.compile(r"^(?:[（(][A-D][）)]|[A-D][\.．、])")

FOOTER_MARKERS = (
    "注：篇幅有限",
    "下载真题及答案解析",
    "为考生提供从复习",
    "特色：名师辅导",
)

QUESTION_START = re.compile(
    r"^(\d+)[、.．]\s*(.*)$"
)
OPTION_INLINE = re.compile(
    r"([A-D])[．.、]\s*(.+?)(?=\s+[A-D][．.、]|$)"
)
OPTION_LINE_AIPTA = re.compile(r"^([A-D])[．.、]\s*(.+)$")
OPTION_LINE_BARE = re.compile(r"^([A-D])([^\s\.．、（(].+)$")
OPTION_LINE_PAREN = re.compile(r"^[（(]([A-D])[）)]\s*(.+)$")
ANSWER_TAG_LINE = re.compile(r"^【(?:正确)?答案】[:：]?\s*([A-H])\s*$")
ANSWER_IN_STEM = re.compile(r"[（(]\s*([A-D])\s*[）)]\s*$")
ANSWER_IN_STEM_LOOSE = re.compile(r"[（(]\s*([A-D])\s*[）)]")
ANSWER_REF_BLOCK = re.compile(r"^【参考答案】[:：]?\s*$")


@dataclass
class ParsedQuestion:
    number: int
    question_type: QuestionType
    section_title: str
    stem: str
    options: dict[str, str] | None = None
    answer: str | None = None
    explanation: str | None = None
    raw_text: str = ""


@dataclass
class ParsedPaper:
    subject: str
    year: int
    source_file: str
    title: str
    questions: list[ParsedQuestion] = field(default_factory=list)
    notes: str | None = None


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_footer(text: str) -> str:
    for marker in FOOTER_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def extract_main_content(text: str) -> str:
    """从噪声较多的 HTML 提取文本中定位正文。"""
    markers = (
        r"以下是\d{4}年",
        r"一、单项选择题",
        r"一、选择题",
        r"第Ⅰ卷",
        r"^选择题\s*$",
        r"词汇和语法结构",
    )
    for pattern in markers:
        m = re.search(pattern, text, flags=re.MULTILINE)
        if m:
            return text[m.start() :].strip()
    return text


SECTION_HEADER = re.compile(
    r"^[一二三四五六七八九十\d]+[、.．]"
    r"(?:"
    r"选择(?:题)?|单项选择(?:题)?|问答题|辨析题|简答题|论述题|"
    r"案例分析题|案例(?:分析)?题?|非选择题"
    r")"
    r"(?:\s*每小题\d+分.*)?$"
)


def detect_section_type(line: str) -> QuestionType | None:
    cleaned = line.strip()
    if not cleaned or OPTION_LINE_HINT.match(cleaned):
        return None
    if SECTION_HEADER.match(cleaned):
        for pattern, qtype in SECTION_TYPE_MAP:
            if pattern.search(cleaned):
                return qtype
    # 爱真题英语：节标题无「一、」前缀
    if len(cleaned) <= 24:
        for pattern, qtype in SECTION_TYPE_MAP:
            if pattern.search(cleaned):
                return qtype
    if cleaned in ("简答题", "论述题", "选择题", "阅读理解", "语音题", "日常对话题", "作文"):
        for pattern, qtype in SECTION_TYPE_MAP:
            if pattern.search(cleaned):
                return qtype
    return None


def parse_options_from_line(line: str) -> dict[str, str]:
    """从单行解析一个或多个选项（支持 A．… B．… 同行排版）。"""
    stripped = line.strip()
    options: dict[str, str] = {}
    for m in OPTION_INLINE.finditer(stripped):
        options[m.group(1)] = m.group(2).strip()
    if options:
        return options
    m = (
        OPTION_LINE_AIPTA.match(stripped)
        or OPTION_LINE_PAREN.match(stripped)
        or OPTION_LINE_BARE.match(stripped)
    )
    if m:
        return {m.group(1): m.group(2).strip()}
    return {}


def parse_options_from_lines(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    options: dict[str, str] = {}
    remainder: list[str] = []
    last_option_key: str | None = None

    for line in lines:
        stripped = line.strip()
        line_opts = parse_options_from_line(line)
        if line_opts:
            options.update(line_opts)
            last_option_key = max(line_opts)
        elif last_option_key and stripped and not stripped.startswith("【"):
            options[last_option_key] = f"{options[last_option_key]} {stripped}".strip()
        else:
            remainder.append(line)
            last_option_key = None
    return options, remainder


def parse_inline_options(stem: str) -> tuple[str, dict[str, str]]:
    """解析题干末尾同行的 A．… B．… 选项。"""
    options: dict[str, str] = {}
    for m in OPTION_INLINE.finditer(stem):
        options[m.group(1)] = m.group(2).strip()

    if options:
        first_opt = re.search(r"[A-D][．.、]", stem)
        if first_opt:
            stem = stem[: first_opt.start()].strip()

    return stem, options


def extract_answer_from_stem(stem: str) -> tuple[str, str | None]:
    m = ANSWER_IN_STEM.search(stem)
    if not m:
        m = ANSWER_IN_STEM_LOOSE.search(stem)
    if not m:
        return stem, None
    answer = m.group(1)
    stem = stem[: m.start()].strip()
    return stem, answer


def is_subjective_block(lines: list[str]) -> bool:
    joined = "\n".join(lines)
    return bool(re.search(r"请回答|案例|每小题\d+分", joined))


def parse_subjective_question(
    number: int,
    qtype: QuestionType,
    section_title: str,
    body_lines: list[str],
) -> ParsedQuestion:
    raw = "\n".join(body_lines).strip()
    stem = raw
    answer = None
    explanation = None

    for tag in ("【参考答案】", "【正确答案】"):
        if tag in raw:
            parts = re.split(rf"{re.escape(tag)}[:：]?\s*", raw, maxsplit=1)
            stem = parts[0].strip()
            if len(parts) > 1:
                answer = parts[1].strip()
            break

    return ParsedQuestion(
        number=number,
        question_type=qtype,
        section_title=section_title,
        stem=stem,
        answer=answer,
        explanation=explanation,
        raw_text=raw,
    )


def parse_choice_question(
    number: int,
    section_title: str,
    first_line: str,
    following_lines: list[str],
) -> ParsedQuestion | None:
    stem_part = first_line
    stem_part, answer = extract_answer_from_stem(stem_part)
    stem_part, inline_opts = parse_inline_options(stem_part)

    option_lines: list[str] = []
    explanation: str | None = None
    for line in following_lines:
        stripped = line.strip()
        am = ANSWER_TAG_LINE.match(stripped)
        if am:
            if answer is None:
                answer = am.group(1)
            continue
        if stripped in ("【正确答案】", "【正确答案】:", "【正确答案】："):
            continue
        if stripped.startswith("【试题解析】"):
            explanation = re.sub(r"^【试题解析】[:：]?\s*", "", stripped).strip()
            continue
        option_lines.append(line)

    extra_opts, remainder = parse_options_from_lines(option_lines)
    options = {**inline_opts, **extra_opts}

    if remainder and not options:
        stem_part = (stem_part + "\n" + "\n".join(remainder)).strip()
    elif remainder and options:
        stem_part = (stem_part + "\n" + "\n".join(remainder)).strip()

    if not stem_part:
        stem_part = section_title or f"第{number}题"

    if not stem_part and not options:
        return None

    raw_parts = [first_line, *following_lines]
    return ParsedQuestion(
        number=number,
        question_type=QuestionType.CHOICE,
        section_title=section_title,
        stem=stem_part,
        options=options or None,
        answer=answer,
        explanation=explanation,
        raw_text="\n".join(raw_parts).strip(),
    )


def infer_subjective_type(section_title: str, stem: str) -> QuestionType:
    joined = f"{section_title}\n{stem}"
    if re.search(r"辨析", joined):
        return QuestionType.OTHER
    if re.search(r"论述|试述|试论", joined):
        return QuestionType.ESSAY
    if re.search(r"案例|请回答", joined):
        return QuestionType.CASE_ANALYSIS
    return QuestionType.SHORT_ANSWER


def parse_text_content(text: str) -> list[ParsedQuestion]:
    text = normalize_text(strip_footer(extract_main_content(text)))
    lines = text.splitlines()

    questions: list[ParsedQuestion] = []
    current_section = ""
    current_type = QuestionType.CHOICE
    subjective_base: int | None = None
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        section_type = detect_section_type(line)
        if section_type:
            current_section = line
            current_type = section_type
            if section_type == QuestionType.CHOICE:
                subjective_base = None
            elif questions and max(q.number for q in questions) >= 20:
                subjective_base = max(q.number for q in questions)
            i += 1
            continue

        if line.startswith("第Ⅱ卷") or line.startswith("第I卷"):
            i += 1
            continue

        m = QUESTION_START.match(line)
        if not m:
            i += 1
            continue

        raw_number = int(m.group(1))
        if (
            current_type != QuestionType.CHOICE
            and subjective_base is not None
            and raw_number <= 15
        ):
            number = subjective_base + raw_number
        else:
            number = raw_number
        rest = m.group(2).strip()
        body_lines: list[str] = []
        j = i + 1

        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                j += 1
                continue
            if detect_section_type(nxt):
                break
            if QUESTION_START.match(nxt):
                break
            if ANSWER_REF_BLOCK.match(nxt):
                break
            body_lines.append(lines[j].rstrip())
            j += 1

        qtype = current_type
        if is_subjective_block([rest, *body_lines]):
            if qtype == QuestionType.CHOICE:
                qtype = QuestionType.CASE_ANALYSIS
        elif current_type != QuestionType.CHOICE:
            qtype = infer_subjective_type(current_section, rest)

        if qtype == QuestionType.CHOICE:
            q = parse_choice_question(number, current_section, rest, body_lines)
            if q:
                questions.append(q)
        else:
            block = [rest, *body_lines]
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                if QUESTION_START.match(nxt) or detect_section_type(nxt):
                    break
                if ANSWER_REF_BLOCK.match(nxt):
                    j += 1
                    answer_lines: list[str] = []
                    while j < len(lines):
                        ans_line = lines[j].strip()
                        if not ans_line:
                            j += 1
                            continue
                        if QUESTION_START.match(ans_line) or detect_section_type(ans_line):
                            break
                        answer_lines.append(lines[j].rstrip())
                        j += 1
                    if answer_lines:
                        block.append("【参考答案】:")
                        block.extend(answer_lines)
                    break
                block.append(lines[j].rstrip())
                j += 1

            questions.append(
                parse_subjective_question(number, qtype, current_section, block)
            )

        i = j

    return deduplicate_questions(questions)


def question_score(q: ParsedQuestion) -> int:
    score = len(q.stem)
    if q.options:
        score += 100
    if q.answer:
        score += 50
    if q.explanation:
        score += 25
    return score


def deduplicate_questions(questions: list[ParsedQuestion]) -> list[ParsedQuestion]:
    best: dict[int, ParsedQuestion] = {}
    for q in questions:
        existing = best.get(q.number)
        if existing is None or question_score(q) > question_score(existing):
            best[q.number] = q
    return [best[n] for n in sorted(best)]


EXAM_YEAR_MARKER = re.compile(
    r"(\d{4})年(?:成人高等学校招生全国统一考试|成人高考|成人尚等学校招生全国统一考试|成人高等)[^\n]{0,40}(?:专升本)?"
)
IMAGE_SECTION = re.compile(r"^===== (.+\.(?:jpg|jpeg|png|webp)) =====$", re.I)


def strip_ocr_image_headers(text: str) -> str:
    return IMAGE_SECTION.sub("", text)


def split_ocr_by_year(text: str) -> list[tuple[int, str]]:
    """将 bb OCR 合并文本按试卷年份拆成多段。"""
    text = strip_ocr_image_headers(text)
    matches = list(EXAM_YEAR_MARKER.finditer(text))
    if not matches:
        return []

    sections: list[tuple[int, str]] = []
    for idx, match in enumerate(matches):
        year = int(match.group(1))
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            sections.append((year, chunk))
    return sections


def merge_ocr_sections(sections: list[tuple[int, str]]) -> dict[int, str]:
    merged: dict[int, list[str]] = {}
    for year, chunk in sections:
        merged.setdefault(year, []).append(chunk)
    return {year: "\n\n".join(parts) for year, parts in merged.items()}


def parse_bb_ocr_file(path: Path) -> list[ParsedPaper]:
    subject = path.parent.parent.name
    text = path.read_text(encoding="utf-8")
    sections = split_ocr_by_year(text)
    papers: list[ParsedPaper] = []

    if sections:
        for year, chunk in merge_ocr_sections(sections).items():
            questions = parse_text_content(chunk)
            papers.append(
                ParsedPaper(
                    subject=subject,
                    year=year,
                    source_file=f"bb/{subject}_{year}_ocr.txt",
                    title=f"{subject} {year} bb OCR",
                    questions=questions,
                    notes="来源: bb 截图 OCR，建议人工校对",
                )
            )
        return sorted(papers, key=lambda p: p.year, reverse=True)

    questions = parse_text_content(strip_ocr_image_headers(text))
    papers.append(
        ParsedPaper(
            subject=subject,
            year=0,
            source_file=f"bb/{path.name}",
            title=f"{subject} bb OCR",
            questions=questions,
            notes="来源: bb 截图 OCR，未识别年份",
        )
    )
    return papers


def discover_bb_ocr_files(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("*/bb/*_ocr.txt") if p.is_file())


def infer_subject_year(path: Path) -> tuple[str, int]:
    parts = path.parts
    year = int(path.parent.name)
    subject = path.parent.parent.name
    return subject, year


def parse_file(path: Path) -> ParsedPaper:
    subject, year = infer_subject_year(path)
    text = path.read_text(encoding="utf-8")
    title = path.stem

    notes = None
    if len(text.strip()) < 200 and "OCR" in text:
        notes = "需 OCR，暂未解析题目"

    questions = parse_text_content(text) if not notes else []

    return ParsedPaper(
        subject=subject,
        year=year,
        source_file=str(path.name),
        title=title,
        questions=questions,
        notes=notes,
    )


def discover_txt_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*.txt")
        if p.name != "README.md" and p.parent.name.isdigit()
    )
