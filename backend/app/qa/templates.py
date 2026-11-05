"""뉴스 질문 유형별 답변 틀(지시문 v5, 2026-11-05). 7단계 실험과 서비스 공용.

게임 공지 질문은 대부분 몇 가지 유형이라, 유형마다 칸을 정해 두고 모델은 칸만 채운다(Ollama `format` JSON 스키마).
자유 요약에서 보이던 뭉뚱그림·수십 개 나열을 칸 개수로 막고, 화면은 유형별로 같은 모양으로 그린다.
- 유형 판별은 질문 단어 규칙(예측 가능·테스트 가능). 애매하면 OTHER(자유 답).
- "(최신 업데이트)" 표시와 최신 공지 고정은 UPDATE_SUMMARY에만 쓴다. 값 질문에 최신 공지를 넣으면 그 공지에
  값이 없을 때 "근거 없음"으로 답하는 부작용이 있었다(v4 재실험 Q13).
이전 지시문 이력: v1 한 줄 답 → v2 설명형 요약 허용 → v3 분야별 예시 → v4 최신 업데이트 표시(DEVLOG 8단계).
"""

import json
import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError

PROMPT_VERSION = "v5"
REFUSAL = "근거 없음"
# 지시와 다른 말로 거절하는 경우(7단계 스모크 실행에서 "정보 없음" 관측)
REFUSALS = (REFUSAL, "정보 없음", "알 수 없", "찾을 수 없", "언급되지 않", "언급이 없")
MAX_ITEMS = 2  # 업데이트 요약의 분야별 항목 수
MAX_FIELD_CHARS = 300

_DOC_ID = re.compile(r"\bN\d{3}\b")
# 답 속 내부 문서 번호("(N047)", "[N012, N013]")는 사용자에게 의미가 없어 지운다
_BRACKETED_ID = re.compile(r"[ \t]*[(\[]N\d{3}(?:\s*,\s*N\d{3})*[)\]]")


class QaIntent(StrEnum):
    UPDATE_SUMMARY = "UPDATE_SUMMARY"
    VALUE = "VALUE"
    SCHEDULE = "SCHEDULE"
    OTHER = "OTHER"


# 순서가 중요하다: "피해량은 언제 바뀌었나"는 값, "바뀐 점"은 요약, "언제 끝나나"는 일정
_VALUE_WORDS = re.compile(
    r"얼마|몇|수치|피해량|데미지|대미지|쿨다운|재사용|가격|확률|체력|공격력|방어력|damage|cooldown|price", re.IGNORECASE
)
_SUMMARY_WORDS = re.compile(
    # "패치노트"만으로는 요약 질문이 아니다("2.4.1 패치노트의 알려진 문제는?" 같은 출처 지칭)
    r"바뀐\s*(점|것|내용)|변경\s*(사항|점|내용)|변경점|(패치|업데이트)\s*내용|요약|달라진|"
    r"새로운\s*(점|것)|(뭐|무엇)(가|이)\s*(바뀌|달라)|추가된\s*(기능|것|점)|고친\s*(버그|것)",
    re.IGNORECASE,
)
_SCHEDULE_WORDS = re.compile(r"언제|기간|일정|점검|시작|종료|마감|까지")


def classify(question: str) -> QaIntent:
    if _VALUE_WORDS.search(question):
        return QaIntent.VALUE
    if _SUMMARY_WORDS.search(question):
        return QaIntent.UPDATE_SUMMARY
    if _SCHEDULE_WORDS.search(question):
        return QaIntent.SCHEDULE
    return QaIntent.OTHER


_COMMON = (
    "너는 게임 뉴스 질의응답 도우미다. 아래 제공된 문서만 근거로 정해진 JSON 칸을 한국어로 채운다. "
    "문서에 없는 내용은 추측하지 않는다.\n"
    "문서마다 [N000] 형식의 ID와 날짜가 있다. sources에는 답에 사용한 문서 ID(예: N012)만 쓴다.\n"
)
_INSTRUCTIONS = {
    QaIntent.UPDATE_SUMMARY: (
        "질문은 업데이트에서 무엇이 바뀌었는지 묻는다. 제목 앞에 '(최신 업데이트)'가 붙은 문서는 가장 최근 패치 공지다. "
        "질문이 특정 버전·날짜를 말하면 그 업데이트를, 아니면 '(최신 업데이트)' 문서를 요약한다.\n"
        "- version: 요약한 업데이트의 버전(없으면 빈 문자열)\n"
        "- date: 그 문서의 날짜\n"
        f"- new_features, balance, bug_fixes: 새 기능 / 밸런스 조정 / 버그 수정을 각각 최대 {MAX_ITEMS}개. "
        "문서에 나온 구체적인 이름과 수치를 그대로 쓴다(예: 'Unholy Trident 피해량 88 → 150'). "
        "'여러 버그 수정'처럼 뭉뚱그리지 않는다. 해당 내용이 없으면 빈 목록.\n"
        "문서에 요약할 업데이트가 없으면 모든 목록을 비운다."
    ),
    QaIntent.VALUE: (
        "질문은 어떤 대상의 값(수치·이름·버전·횟수 등)을 묻는다.\n"
        "- target: 질문이 묻는 대상(예: 'Arc Lance 피해량')\n"
        "- value: 답이 되는 값. 질문이 특정 버전·문서를 말하면 그 기준, 아니면 그 값을 언급한 문서 중 날짜가 가장 늦은 "
        "문서 기준의 현재 값. 횟수·차이·여러 버전을 물으면 그 답(예: '3', '2.3.0, 2.4.1'). 문서에 없으면 '근거 없음'\n"
        "- changed_in: 그 값으로 바뀐 버전 또는 날짜(모르면 빈 문자열)\n"
        "- previous: 바뀌기 전 값(모르면 빈 문자열)"
    ),
    QaIntent.SCHEDULE: (
        "질문은 이벤트·점검·출시 같은 일정을 묻는다.\n"
        "- name: 일정의 이름. 문서에 없으면 '근거 없음'\n"
        "- start: 시작 날짜·시각(모르면 빈 문자열)\n"
        "- end: 종료 날짜·시각(모르면 빈 문자열)"
    ),
    QaIntent.OTHER: "- answer: 질문에 대한 짧고 구체적인 답. 문서에 없으면 '근거 없음'",
}

_STR = {"type": "string"}
_SOURCES = {"type": "array", "items": _STR, "maxItems": 5}


def _list(n: int) -> dict:
    return {"type": "array", "items": _STR, "maxItems": n}


_SCHEMAS = {
    QaIntent.UPDATE_SUMMARY: {"version": _STR, "date": _STR, "new_features": _list(MAX_ITEMS),
                              "balance": _list(MAX_ITEMS), "bug_fixes": _list(MAX_ITEMS), "sources": _SOURCES},
    QaIntent.VALUE: {"target": _STR, "value": _STR, "changed_in": _STR, "previous": _STR, "sources": _SOURCES},
    QaIntent.SCHEDULE: {"name": _STR, "start": _STR, "end": _STR, "sources": _SOURCES},
    QaIntent.OTHER: {"answer": _STR, "sources": _SOURCES},
}


def system_prompt(intent: QaIntent) -> str:
    return _COMMON + _INSTRUCTIONS[intent]


def json_schema(intent: QaIntent) -> dict:
    props = _SCHEMAS[intent]
    return {"type": "object", "properties": props, "required": list(props)}


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class UpdateSummary(_Loose):
    version: str = ""
    date: str = ""
    new_features: list[str] = []
    balance: list[str] = []
    bug_fixes: list[str] = []
    sources: list[str] = []


class ValueAnswer(_Loose):
    target: str = ""
    value: str = ""
    changed_in: str = ""
    previous: str = ""
    sources: list[str] = []


class ScheduleAnswer(_Loose):
    name: str = ""
    start: str = ""
    end: str = ""
    sources: list[str] = []


class OtherAnswer(_Loose):
    answer: str = ""
    sources: list[str] = []


_MODELS: dict[QaIntent, type[_Loose]] = {
    QaIntent.UPDATE_SUMMARY: UpdateSummary,
    QaIntent.VALUE: ValueAnswer,
    QaIntent.SCHEDULE: ScheduleAnswer,
    QaIntent.OTHER: OtherAnswer,
}

Filled = UpdateSummary | ValueAnswer | ScheduleAnswer | OtherAnswer


def _clean(text: str, titles: dict[str, str]) -> str:
    text = text.strip()
    # 칸 전체가 문서 번호뿐이면(예: 버전을 묻는데 "[N122]") 그 공지 제목으로 바꾼다 — 지우면 빈 답이 된다
    only_ids = _DOC_ID.findall(text)
    if only_ids and not _DOC_ID.sub("", text).strip(" ,[]()"):
        return ", ".join(titles.get(i, "") for i in only_ids).strip(", ")[:MAX_FIELD_CHARS]
    return _BRACKETED_ID.sub("", text).strip()[:MAX_FIELD_CHARS]


def _is_refusal(text: str) -> bool:
    return not text or any(p in text for p in REFUSALS)


def parse(intent: QaIntent, content: str, titles: dict[str, str] | None = None) -> Filled | None:
    """모델 JSON을 유형별 칸으로. titles = 문서 ID → 제목. 형식이 깨졌으면(출력 한도에서 잘림 등) None."""
    titles = titles or {}
    try:
        raw = json.loads(content.rsplit("</think>", 1)[-1])
        filled = _MODELS[intent].model_validate(raw)
    except (ValueError, ValidationError):
        return None
    data = filled.model_dump()
    for key, val in data.items():
        if key == "sources":
            data[key] = list(dict.fromkeys(i for s in val for i in _DOC_ID.findall(s)))
        elif isinstance(val, list):
            data[key] = [c for v in val if (c := _clean(v, titles))][:MAX_ITEMS]
        else:
            data[key] = _clean(val, titles)
    return _MODELS[intent].model_validate(data)


def render(filled: Filled) -> tuple[str, bool]:
    """(한 줄·여러 줄 답변 문장, 거절 여부). 화면 공용 표시와 실험 채점에 쓴다."""
    if isinstance(filled, UpdateSummary):
        sections = [("새 기능", filled.new_features), ("밸런스 조정", filled.balance), ("버그 수정", filled.bug_fixes)]
        lines = [f"- {label}: {'; '.join(items)}" for label, items in sections if items]
        if not lines:
            return REFUSAL, True
        head = " ".join(p for p in (filled.version, f"({filled.date})" if filled.date else "") if p)
        return "\n".join(([head] if head else []) + lines), False
    if isinstance(filled, ValueAnswer):
        if _is_refusal(filled.value):
            return REFUSAL, True
        detail = ""
        if filled.changed_in and filled.previous:
            detail = f" ({filled.changed_in}에서 {filled.previous} → {filled.value})"
        elif filled.changed_in:
            detail = f" ({filled.changed_in})"
        return filled.value + detail, False
    if isinstance(filled, ScheduleAnswer):
        if _is_refusal(filled.name) or not (filled.start or filled.end):
            return REFUSAL, True
        if not filled.end:  # 출시일처럼 하루짜리 일정
            return f"{filled.name}: {filled.start}", False
        return f"{filled.name}: {filled.start or '?'} ~ {filled.end}", False
    if _is_refusal(filled.answer):
        return REFUSAL, True
    return filled.answer, False
