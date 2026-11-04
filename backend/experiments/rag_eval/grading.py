"""자동 채점. 정확한 판정은 수동 확인 표본으로 보완한다(PRD).

모델에게 "답: … / 근거: …" 형식을 요구하고 "답:" 줄만 채점한다(추론 문장 속 숫자에 속지 않게).
"""

import re
from dataclasses import dataclass

REFUSAL = "근거 없음"
# 지시와 다른 말로 거절하는 경우(2k 스모크 실행에서 "정보 없음" 관측)
REFUSALS = (REFUSAL, "정보 없음", "알 수 없", "찾을 수 없", "언급되지 않", "언급이 없")
# Q34처럼 "그 버전에서 바뀌지 않았다"도 맞는 답 없음 질문용
NO_CHANGE = ("변경 없음", "바뀌지 않", "변경되지 않", "변경이 없", "변동 없음")
_DOC_ID = re.compile(r"\bN\d{3}\b")
_NUMERIC = re.compile(r"^[\d.]+$")


@dataclass(frozen=True)
class Grade:
    correct: bool
    refused: bool
    answer_line: str
    cited: list[str]


def final_text(content: str) -> str:
    """Thinking 모델의 추론 부분(</think> 앞)을 버린다."""
    return content.rsplit("</think>", 1)[-1].strip()


def _answer_line(text: str) -> str:
    for line in text.splitlines():
        m = re.match(r"\s*\**\s*답\s*\**\s*[:：]\s*(.*)", line)
        if m:
            return m.group(1).strip()
    return text.strip()  # 형식을 안 지키면 전체를 본다


def _cited(text: str) -> list[str]:
    for line in text.splitlines():
        if re.match(r"\s*\**\s*근거\s*\**\s*[:：]", line):
            return sorted(set(_DOC_ID.findall(line)))
    return sorted(set(_DOC_ID.findall(text)))


def _matches(option: str, text: str) -> bool:
    if _NUMERIC.match(option):
        # "50"이 "150"·"50.5"·"2.50"에 걸리지 않게 앞뒤가 숫자·소수점이 아니어야 한다
        return re.search(rf"(?<![\d.]){re.escape(option)}(?!\d|\.\d)", text) is not None
    # 모델이 "11 월 3 일"처럼 띄어 쓰기도 해 공백을 무시한다
    return _squash(option) in _squash(text)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def grade(content: str, answer: list[list[str]]) -> Grade:
    text = final_text(content)
    line = _answer_line(text)
    refused = any(p in line for p in REFUSALS)
    if not answer:  # 답 없음 질문
        correct = refused or any(p in line for p in NO_CHANGE)
    else:
        correct = not refused and all(any(_matches(o, line) for o in options) for options in answer)
    return Grade(correct, refused, line, _cited(text))
