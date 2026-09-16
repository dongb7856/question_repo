"""从 OCR 文本中解析真题（适配 bb 截图）。"""

from __future__ import annotations

import re
from pathlib import Path

from parse_questions import (
    ParsedPaper,
    ParsedQuestion,
    QuestionType,
    deduplicate_questions,
    parse_text_content,
)

YEAR_HEADER = re.compile(r"(20[12]\d)年成人.*?全国统一.*?专升本(政治|民法)", re.I)
CHOICE_ANSWER = re.compile(
    r"(\d+)[.．、:：]?\s*[【\[]?\s*答案\s*[】\]]?\s*([A-D])",
)
SUBJECTIVE_ANSWER = re.compile(
    r"(\d+)[.．、:：]?\s*[【\[]?\s*答案\s*[】\]]?\s*\n(.*?)(?=\n\d+[.．、:：]?\s*[【\[]?\s*答案|\n【考情点拨】|\Z)",
    re.S,
)
QUESTION_LINE = re.compile(r"^(\d+)[.、．]\s*(.+)$")
OPTION_LINE = re.compile(r"^([A-D])[.．、]\s*(.+)$")
SUBJECTIVE_HINT = re.compile(r"简述|试述|论述|简答|案例|请回答|什么是|如何理解|为什么|试论|辨析")
IMAGE_MARKER = re.compile(r"^===== .+ =====$")
STEM_TRAILING_ANSWER = re.compile(r"[（(]\s*([A-D])\s*[）)]\s*$")

_stem_index_cache: dict[str, dict[str, ParsedQuestion]] = {}


def trim_other_years(text: str, year: int) -> str:
    for match in YEAR_HEADER.finditer(text):
        found = int(match.group(1))
        if found != year and match.start() > 0:
            return text[: match.start()].strip()
    return text.strip()


def clean_ocr_text(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or IMAGE_MARKER.match(line):
            continue
        if line in {"【", "】", "【】", "得分", "评卷人", "密", "封", "线", "内", "不"}:
            continue
        if re.fullmatch(r"[A-D]", line):
            continue
        lines.append(line)
    return "\n".join(lines)


def extract_choice_answers(text: str) -> dict[int, str]:
    answers: dict[int, str] = {}
    for num, ans in CHOICE_ANSWER.findall(text):
        n = int(num)
        if 1 <= n <= 35:
            answers[n] = ans
    return answers


def extract_subjective_answers(text: str) -> dict[int, str]:
    answers: dict[int, str] = {}
    for match in SUBJECTIVE_ANSWER.finditer(text):
        num = int(match.group(1))
        body = re.sub(r"\s+", " ", match.group(2)).strip()
        body = re.sub(r"^【考情点拨】.*", "", body).strip()
        if len(body) >= 20:
            answers[num] = body
    return answers


def infer_question_type(number: int, stem: str) -> QuestionType:
    if SUBJECTIVE_HINT.search(stem):
        if "案例" in stem or "请回答" in stem:
            return QuestionType.CASE_ANALYSIS
        if "论述" in stem or "试述" in stem or "试论" in stem:
            return QuestionType.ESSAY
        if "辨析" in stem:
            return QuestionType.OTHER
        return QuestionType.SHORT_ANSWER
    if number >= 36:
        return QuestionType.SHORT_ANSWER
    return QuestionType.CHOICE


def extract_question_candidates(text: str) -> dict[int, list[ParsedQuestion]]:
    candidates: dict[int, list[ParsedQuestion]] = {}
    lines = text.splitlines()
    i = 0
    section = "OCR"

    while i < len(lines):
        line = lines[i].strip()
        m = QUESTION_LINE.match(line)
        if not m:
            i += 1
            continue

        number = int(m.group(1))
        rest = m.group(2).strip()
        if "答案" in rest[:6]:
            i += 1
            continue

        body: list[str] = []
        options: dict[str, str] = {}
        j = i + 1
        while j < len(lines) and j < i + 8:
            nxt = lines[j].strip()
            if not nxt:
                j += 1
                continue
            if QUESTION_LINE.match(nxt):
                break
            if re.match(r"^\d+\.[【\[]?答案", nxt):
                break
            opt = OPTION_LINE.match(nxt)
            if opt:
                options[opt.group(1)] = opt.group(2).strip()
            else:
                body.append(nxt)
            j += 1

        stem = rest
        if body and infer_question_type(number, rest) == QuestionType.CHOICE:
            stem = rest

        qtype = infer_question_type(number, stem + " ".join(body))
        if qtype != QuestionType.CHOICE:
            stem = "\n".join([rest, *body]).strip()

        q = ParsedQuestion(
            number=number,
            question_type=qtype,
            section_title=section,
            stem=stem,
            options=options or None,
            raw_text="\n".join([line, *body]).strip(),
        )
        candidates.setdefault(number, []).append(q)
        i = j if j > i + 1 else i + 1

    return candidates


def normalize_stem(stem: str) -> str:
    text = STEM_TRAILING_ANSWER.sub("", stem.strip())
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。、；：:!！?？（）()【】\[\]]", "", text)
    return text


def choice_options_incomplete(q: ParsedQuestion) -> bool:
    if q.question_type != QuestionType.CHOICE:
        return False
    opts = q.options or {}
    return len(opts) < 4


def build_stem_option_index(subject: str, questions_root: Path) -> dict[str, ParsedQuestion]:
    cache_key = f"{subject}:{questions_root}"
    if cache_key in _stem_index_cache:
        return _stem_index_cache[cache_key]

    index: dict[str, ParsedQuestion] = {}
    subject_dir = questions_root / subject
    if not subject_dir.is_dir():
        _stem_index_cache[cache_key] = index
        return index

    for year_dir in sorted(subject_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for path in sorted(year_dir.glob("*.txt")):
            if "OCR" in path.read_text(encoding="utf-8", errors="ignore")[:200]:
                continue
            for q in parse_text_content(path.read_text(encoding="utf-8")):
                if q.question_type != QuestionType.CHOICE or not q.options:
                    continue
                if len(q.options) < 4:
                    continue
                key = normalize_stem(q.stem)
                if len(key) < 8:
                    continue
                existing = index.get(key)
                if not existing or len(q.stem) > len(existing.stem):
                    index[key] = q

    _stem_index_cache[cache_key] = index
    return index


def find_stem_match(stem: str, index: dict[str, ParsedQuestion]) -> ParsedQuestion | None:
    key = normalize_stem(stem)
    if len(key) < 8:
        return None

    if key in index:
        return index[key]

    best: ParsedQuestion | None = None
    best_len = 0
    for candidate_key, q in index.items():
        if key in candidate_key or candidate_key in key:
            overlap = min(len(key), len(candidate_key))
            if overlap > best_len:
                best = q
                best_len = overlap
    return best if best_len >= max(12, int(len(key) * 0.7)) else None


def enrich_incomplete_options(
    questions: list[ParsedQuestion],
    stem_index: dict[str, ParsedQuestion],
) -> list[ParsedQuestion]:
    enriched: list[ParsedQuestion] = []
    for q in questions:
        if not choice_options_incomplete(q):
            enriched.append(q)
            continue

        match = find_stem_match(q.stem, stem_index)
        if match and match.options:
            enriched.append(
                ParsedQuestion(
                    number=q.number,
                    question_type=QuestionType.CHOICE,
                    section_title=q.section_title or match.section_title,
                    stem=match.stem if len(match.stem) > len(q.stem) else q.stem,
                    options=match.options,
                    answer=q.answer or match.answer,
                    explanation=q.explanation or match.explanation,
                    raw_text=q.raw_text or match.raw_text,
                )
            )
        else:
            enriched.append(q)
    return enriched


def pick_best_candidate(items: list[ParsedQuestion]) -> ParsedQuestion:
    def score(q: ParsedQuestion) -> int:
        s = len(q.stem)
        if q.options:
            s += len(q.options) * 30
        if SUBJECTIVE_HINT.search(q.stem):
            s += 40
        if q.question_type != QuestionType.CHOICE:
            s += 20
        return s

    return max(items, key=score)


def merge_with_txt(year_text: ParsedPaper | None, ocr_questions: list[ParsedQuestion]) -> list[ParsedQuestion]:
    if not year_text or not year_text.questions:
        return ocr_questions

    txt_map = {q.number: q for q in year_text.questions}
    merged: dict[int, ParsedQuestion] = {}

    for q in ocr_questions:
        base = txt_map.get(q.number)
        needs_stem = len(q.stem) < 12
        needs_options = q.question_type == QuestionType.CHOICE and choice_options_incomplete(q)
        if base and (needs_stem or (needs_options and base.options)):
            merged[q.number] = ParsedQuestion(
                number=q.number,
                question_type=base.question_type,
                section_title=base.section_title or q.section_title,
                stem=base.stem if needs_stem or len(base.stem) > len(q.stem) else q.stem,
                options=base.options if needs_options else q.options,
                answer=q.answer or base.answer,
                explanation=base.explanation,
                raw_text=base.raw_text or q.raw_text,
            )
        else:
            merged[q.number] = q

    for num, base in txt_map.items():
        if num not in merged:
            merged[num] = base

    return [merged[n] for n in sorted(merged)]


def parse_ocr_text(
    text: str,
    txt_fallback: ParsedPaper | None = None,
    year: int | None = None,
    stem_index: dict[str, ParsedQuestion] | None = None,
) -> list[ParsedQuestion]:
    if year is not None:
        text = trim_other_years(text, year)
    cleaned = clean_ocr_text(text)
    choice_answers = extract_choice_answers(cleaned)
    subjective_answers = extract_subjective_answers(cleaned)
    candidates = extract_question_candidates(cleaned)

    questions: list[ParsedQuestion] = []
    all_numbers = sorted(set(candidates) | set(choice_answers) | set(subjective_answers))

    for number in all_numbers:
        if number in candidates:
            q = pick_best_candidate(candidates[number])
        else:
            q = ParsedQuestion(
                number=number,
                question_type=QuestionType.CHOICE if number <= 35 else QuestionType.SHORT_ANSWER,
                section_title="OCR",
                stem="",
            )

        if number in choice_answers:
            q.question_type = QuestionType.CHOICE
            q.answer = choice_answers[number]
        elif number in subjective_answers:
            q.answer = subjective_answers[number]
            if q.question_type == QuestionType.CHOICE:
                q.question_type = infer_question_type(number, q.stem or "")

        if number in subjective_answers and (not q.stem or len(q.stem) < 8):
            for cand in candidates.get(number, []):
                if len(cand.stem) >= 8:
                    q.stem = cand.stem
                    q.question_type = cand.question_type
                    break

        if q.stem or q.answer:
            questions.append(q)

    questions = deduplicate_questions(questions)
    questions = merge_with_txt(txt_fallback, questions)
    if stem_index:
        questions = enrich_incomplete_options(questions, stem_index)
    return questions


def find_txt_fallback(subject: str, year: int, questions_root: Path) -> ParsedPaper | None:
    year_dir = questions_root / subject / str(year)
    if not year_dir.is_dir():
        return None

    txts = sorted(year_dir.glob("*.txt"))
    if not txts:
        return None

    best: ParsedPaper | None = None
    for path in txts:
        paper = ParsedPaper(
            subject=subject,
            year=year,
            source_file=path.name,
            title=path.stem,
            questions=parse_text_content(path.read_text(encoding="utf-8")),
        )
        if not best or len(paper.questions) > len(best.questions):
            best = paper
    return best


def parse_bb_year_file(path: Path, questions_root: Path) -> ParsedPaper:
    subject = path.parent.parent.name
    year = int(path.stem)
    text = path.read_text(encoding="utf-8")
    fallback = find_txt_fallback(subject, year, questions_root)
    stem_index = build_stem_option_index(subject, questions_root)
    questions = parse_ocr_text(
        text,
        txt_fallback=fallback,
        year=year,
        stem_index=stem_index,
    )

    return ParsedPaper(
        subject=subject,
        year=year,
        source_file=f"bb/{path.name}",
        title=f"{subject}_{year}_bb",
        questions=questions,
        notes="来源: bb 截图 OCR",
    )


def discover_bb_year_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for subject in ("政治", "民法"):
        bb_dir = root / subject / "bb"
        if not bb_dir.is_dir():
            continue
        for path in sorted(bb_dir.glob("*.txt")):
            if path.name.endswith("_bb_ocr.txt"):
                continue
            if path.stem.isdigit() and path.stem.startswith("20"):
                files.append(path)
    return files
