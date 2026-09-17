"""DeepSeek Chat（OpenAI 兼容），与 autoyt2 / web-vehicle 同源环境变量。"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

_CHOICE_ANSWER = re.compile(r"^([A-H])\b", re.I)
_SIMILARITY_THRESHOLD = 70


class LlmNotConfiguredError(RuntimeError):
    pass


class LlmApiError(RuntimeError):
    pass


def _env_nonempty(key: str) -> str | None:
    value = (os.environ.get(key) or "").strip()
    return value or None


def deepseek_config() -> tuple[str, str, str] | None:
    """LLM_API_KEY / LLM_BASE_URL / LLM_MODEL，与 autoyt2 一致。"""
    key = _env_nonempty("LLM_API_KEY")
    if not key:
        return None
    base = (_env_nonempty("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model = _env_nonempty("LLM_MODEL") or "deepseek-chat"
    return key, base, model


def _timeout_seconds() -> float:
    raw = os.environ.get("LLM_HTTP_TIMEOUT_SECONDS", "60").strip() or "60"
    return float(raw)


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def normalize_choice_answer(raw: Any) -> str | None:
    if raw is None:
        return None
    match = _CHOICE_ANSWER.match(str(raw).strip())
    return match.group(1).upper() if match else None


def _choice_letters_hint(options: Any) -> str:
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            return "A/B/C/D"
    if isinstance(options, dict) and options:
        keys = {str(key).upper() for key in options}
        if keys & {"E", "F", "G", "H"}:
            return "A-H"
    return "A/B/C/D"


def _is_gradable_choice(question: dict[str, Any]) -> bool:
    options = question.get("options")
    if not options:
        return False
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            return False
    return isinstance(options, dict) and len(options) >= 2


def chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> tuple[str, str]:
    cfg = deepseek_config()
    if not cfg:
        raise LlmNotConfiguredError("请在 .env 中配置 LLM_API_KEY（可与 autoyt2 共用）")

    key, base, model = cfg
    body: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        with httpx.Client(timeout=_timeout_seconds(), trust_env=False) as client:
            response = client.post(
                f"{base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise LlmApiError(f"调用 DeepSeek 失败：{exc}") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmApiError("DeepSeek 响应格式异常") from exc

    return str(content).strip(), model


def _format_options(options: Any) -> str:
    if not options:
        return "（无选项，为主观题）"
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            return options
    if not isinstance(options, dict):
        return str(options)
    lines = []
    for key in sorted(options):
        lines.append(f"{key}. {options[key]}")
    return "\n".join(lines)


def _parse_similarity_score(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        score = int(float(raw))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _coerce_analysis(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LlmApiError("DeepSeek 返回结构不符合预期")
    return {
        "suggested_answer": str(data.get("suggested_answer") or "").strip(),
        "analysis": str(data.get("analysis") or "").strip(),
        "discrepancy_note": str(data.get("discrepancy_note") or "").strip(),
        "similarity_score": _parse_similarity_score(data.get("similarity_score")),
    }


def _resolve_agreement(
    *,
    is_choice: bool,
    stored_answer: str,
    suggested_answer: str,
    similarity_score: int | None,
    discrepancy_note: str,
) -> tuple[bool, int | None]:
    stored_choice = normalize_choice_answer(stored_answer)
    suggested_choice = normalize_choice_answer(suggested_answer)

    if is_choice and stored_choice and suggested_choice:
        agrees = stored_choice == suggested_choice
        return agrees, 100 if agrees else 0

    if similarity_score is not None:
        return similarity_score >= _SIMILARITY_THRESHOLD, similarity_score

    if is_choice and stored_answer and suggested_answer:
        agrees = stored_answer.strip() == suggested_answer.strip()
        return agrees, 100 if agrees else 0

    agrees = not discrepancy_note
    return agrees, similarity_score


def analyze_question(question: dict[str, Any]) -> dict[str, Any]:
    """独立解题并与题库参考答案对比，供 UI 并排展示。"""
    subject = question.get("subject") or "未知科目"
    year = question.get("year") or "未知年份"
    number = question.get("number") or "?"
    qtype = question.get("question_type") or "other"
    stem = (question.get("stem") or "").strip()
    stored_answer = (question.get("answer") or "").strip()
    explanation = (question.get("explanation") or "").strip()
    options_text = _format_options(question.get("options"))
    is_choice = _is_gradable_choice(question)

    user_bits = [
        f"科目：{subject}",
        f"年份：{year}",
        f"题号：{number}",
        f"题型：{qtype}",
        f"题干：{stem}",
        f"选项：\n{options_text}",
    ]
    if stored_answer:
        user_bits.append(f"题库标注参考答案：{stored_answer}")
    else:
        user_bits.append("题库标注参考答案：（缺失）")
    if explanation:
        user_bits.append(f"题库附带解析：{explanation}")

    choice_letters = _choice_letters_hint(question.get("options"))
    schema_hint = (
        f'{{"suggested_answer":"你的答案（选择题仅 {choice_letters}；主观题写要点）",'
        '"analysis":"独立解题过程与依据，150字内",'
        '"similarity_score":85,'
        '"discrepancy_note":"若与题库参考答案含义明显不一致，说明差异；一致则留空"}'
    )

    choice_rule = (
        f"选择题 suggested_answer 必须是单个 {choice_letters}，"
        "similarity_score 在与题库选项一致时为 100，否则为 0。"
    )
    subjective_rule = (
        "主观题/简答/论述：比较题库参考答案与你的 suggested_answer 的语义与要点覆盖度，"
        "similarity_score 取 0-100（看含义，不看字面是否相同）。"
        f"≥{_SIMILARITY_THRESHOLD} 视为基本一致。"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "你是成人高考专升本（政治/民法/英语）审题专家。"
                "请先独立解题，不要默认题库答案正确。"
                "再评估你的答案与题库参考答案在含义上的一致程度。"
                f"{choice_rule if is_choice else subjective_rule}"
                f"仅返回 JSON：{schema_hint}"
            ),
        },
        {"role": "user", "content": "\n".join(user_bits)},
    ]

    raw, model = chat_completion(messages, temperature=0.2, json_mode=True)
    try:
        parsed = _coerce_analysis(json.loads(_strip_json_fence(raw)))
    except json.JSONDecodeError as exc:
        raise LlmApiError("DeepSeek 返回内容不是有效 JSON") from exc

    agrees, similarity_score = _resolve_agreement(
        is_choice=is_choice,
        stored_answer=stored_answer,
        suggested_answer=parsed["suggested_answer"],
        similarity_score=parsed["similarity_score"],
        discrepancy_note=parsed["discrepancy_note"],
    )

    return {
        "model": model,
        "question_type": "choice" if is_choice else "subjective",
        "stored_answer": stored_answer,
        "suggested_answer": parsed["suggested_answer"],
        "analysis": parsed["analysis"],
        "discrepancy_note": parsed["discrepancy_note"],
        "similarity_score": similarity_score,
        "agrees_with_stored": agrees,
    }


def summarize_session(stats: dict[str, Any]) -> dict[str, Any]:
    """根据本轮练习统计生成 DeepSeek 汇总点评。"""
    messages = [
        {
            "role": "system",
            "content": (
                "你是成人高考专升本辅导老师。根据本轮练习统计数据，"
                "用 120 字以内给出简短汇总：正确率评价、薄弱提醒、"
                "以及 DeepSeek 与题库不一致题目是否需要人工核对。简体中文，分段清晰。"
            ),
        },
        {"role": "user", "content": json.dumps(stats, ensure_ascii=False)},
    ]
    text, model = chat_completion(messages, temperature=0.4, json_mode=False)
    return {"summary": text, "model": model}
