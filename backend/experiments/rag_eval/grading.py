"""자동 채점. 정확한 판정은 수동 확인 표본으로 보완한다(PRD).

모델에게 "답: … / 근거: …" 형식을 요구하고 "답:" 줄만 채점한다(추론 문장 속 숫자에 속지 않게).
"""

import re
from dataclasses import dataclass

from app.qa.prompt import answer_line, cited_ids, final_text
from app.qa.templates import REFUSAL, REFUSALS, QaIntent, ValueAnswer, parse, render

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


def structured_content(intent: QaIntent, raw: str, titles: dict[str, str]) -> str:
    """v5 JSON 칸을 채점용 "답: … / 근거: …"로. 값 질문은 값 칸만 본다 —
    화면 문장("50 (55 → 50)")의 이전 값까지 보면 틀린 답이 정답으로 잡힌다(v5 첫 집계에서 발견)."""
    filled = parse(intent, raw, titles)
    if filled is None:
        return "답: (형식 오류)"
    text, refused = render(filled)
    if isinstance(filled, ValueAnswer) and not refused:
        text = filled.value
    return f"답: {REFUSAL if refused else text}\n근거: {', '.join(filled.sources)}"


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
