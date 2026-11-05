"""자동 채점. 정확한 판정은 수동 확인 표본으로 보완한다(PRD).

모델에게 "답: … / 근거: …" 형식을 요구하고 "답:" 줄만 채점한다(추론 문장 속 숫자에 속지 않게).
"""

import json
import re
from dataclasses import dataclass

from app.qa.prompt import answer_line, cited_ids, final_text
from app.qa.templates import REFUSAL, REFUSALS, QaIntent, ValueAnswer, parse, render
from app.qa.value import DocInfo, compute_value

# Q34처럼 "그 버전에서 바뀌지 않았다"도 맞는 답 없음 질문용
NO_CHANGE = ("변경 없음", "바뀌지 않", "변경되지 않", "변경이 없", "변동 없음")
_NUMERIC = re.compile(r"^[\d.]+$")


@dataclass(frozen=True)
class Grade:
    correct: bool
    refused: bool
    answer_line: str
    cited: list[str]


def _matches(option: str, text: str) -> bool:
    if _NUMERIC.match(option):
        # "50"이 "150"·"50.5"·"2.50"에 걸리지 않게 앞뒤가 숫자·소수점이 아니어야 한다
        return re.search(rf"(?<![\d.]){re.escape(option)}(?!\d|\.\d)", text) is not None
    # 모델이 "11 월 3 일"처럼 띄어 쓰기도 해 공백을 무시한다
    return _squash(option) in _squash(text)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def structured_content(intent: QaIntent, raw: str, titles: dict[str, str], question: str = "",
                       docs: dict[str, DocInfo] | None = None, allowed: set[str] | None = None) -> str:
    """v5~v7 JSON 칸을 채점용 "답: … / 근거: …"로. 값 질문은 값 칸만 본다 —
    화면 문장("50 (55 → 50)")의 이전 값까지 보면 틀린 답이 정답으로 잡힌다(v5 첫 집계에서 발견).
    v7 값 질문은 서비스와 같은 서버 계산(compute_value)을 거친다(docs = 문서 ID → 날짜·제목, allowed = 넘긴 문서)."""
    filled = parse(intent, _legacy_schedule(intent, raw), titles)
    if filled is None:
        return "답: (형식 오류)"
    if isinstance(filled, ValueAnswer) and docs is not None:
        filled = compute_value(filled, question, docs, allowed)
    text, refused = render(filled)
    if isinstance(filled, ValueAnswer) and not refused:
        text = filled.value
    return f"답: {REFUSAL if refused else text}\n근거: {', '.join(filled.sources)}"


def _legacy_schedule(intent: QaIntent, raw: str) -> str:
    """v5 일정 칸 {name, start, end}를 v6 {items: [...]}로 — v5 기록을 지금 규칙으로 다시 채점할 때."""
    if intent is not QaIntent.SCHEDULE:
        return raw
    try:
        data = json.loads(final_text(raw))
    except ValueError:
        return raw
    if not isinstance(data, dict) or "items" in data or "name" not in data:
        return raw
    item = {k: data.get(k, "") for k in ("name", "start", "end")}
    return json.dumps({"items": [item], "sources": data.get("sources", [])}, ensure_ascii=False)


def grade(content: str, answer: list[list[str]]) -> Grade:
    text = final_text(content)
    found = answer_line(text)
    line = found if found is not None else text.strip()  # 형식을 안 지키면 전체를 본다
    refused = any(p in line for p in REFUSALS)
    if not answer:  # 답 없음 질문
        correct = refused or any(p in line for p in NO_CHANGE)
    else:
        correct = not refused and all(any(_matches(o, line) for o in options) for options in answer)
    return Grade(correct, refused, line, sorted(set(cited_ids(text))))
