"""뉴스 질문 유형별 답변 틀(지시문 v6, PRD v6.8). 7단계 실험과 서비스 공용.

게임 공지 질문은 대부분 몇 가지 유형이라, 유형마다 칸을 정해 두고 모델은 칸만 채운다(Ollama `format` JSON 스키마).
자유 요약에서 보이던 뭉뚱그림·수십 개 나열을 칸 개수로 막고, 화면은 유형별로 같은 모양으로 그린다.
- 유형 판별은 질문 단어 규칙(예측 가능·테스트 가능). 애매하면 OTHER(자유 답).
- "(최신 업데이트)" 표시와 최신 공지 고정은 UPDATE_SUMMARY에만 쓴다. 값 질문에 최신 공지를 넣으면 그 공지에
  값이 없을 때 "근거 없음"으로 답하는 부작용이 있었다(v4 재실험 Q13).
- 날짜로 정해지는 상태(진행 중·예정·종료)는 모델에 맡기지 않고 서버가 오늘(한국 날짜)과 비교해 정한다 —
  v5에서 이미 끝난 대회를 "진행 중"으로 답했다.
이전 지시문 이력: v1 한 줄 답 → v2 설명형 요약 허용 → v3 분야별 예시 → v4 최신 업데이트 표시
→ v5 유형별 칸 → v6 일정 여러 건·종류, 신규 콘텐츠 틀 → v7 값 질문은 변경 기록만 받고 서버가 계산(value.py)
(DEVLOG 8단계).
"""

import json
import re
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

PROMPT_VERSION = "v7"
REFUSAL = "근거 없음"
# 지시와 다른 말로 거절하는 경우(7단계 스모크 실행에서 "정보 없음" 관측)
REFUSALS = (REFUSAL, "정보 없음", "알 수 없", "찾을 수 없", "언급되지 않", "언급이 없")
MAX_ITEMS = 2  # 업데이트 요약의 분야별 항목 수
MAX_SCHEDULE_ITEMS = 3
MAX_HIGHLIGHTS = 3
MAX_HISTORY = 8
# 한국은 서머타임이 없어 고정 오프셋으로 충분하다(Windows의 zoneinfo는 tzdata 패키지가 따로 필요)
KST = timezone(timedelta(hours=9))
MAX_FIELD_CHARS = 300

_DOC_ID = re.compile(r"\bN\d{3}\b")
# 답 속 내부 문서 번호("(N047)", "[N012, N013]")는 사용자에게 의미가 없어 지운다
_BRACKETED_ID = re.compile(r"[ \t]*[(\[]N\d{3}(?:\s*,\s*N\d{3})*[)\]]")


class QaIntent(StrEnum):
    UPDATE_SUMMARY = "UPDATE_SUMMARY"
    VALUE = "VALUE"
    SCHEDULE = "SCHEDULE"
    CONTENT = "CONTENT"
    OTHER = "OTHER"


class Status(StrEnum):
    ONGOING = "ONGOING"
    UPCOMING = "UPCOMING"
    ENDED = "ENDED"
    UNKNOWN = "UNKNOWN"


ScheduleKind = Literal["EVENT", "RELEASE", "MAINTENANCE", "TEST", "SALE"]
ContentForm = Literal["FREE_UPDATE", "DLC", "EXPANSION", "OTHER"]
_KINDS: tuple[str, ...] = ScheduleKind.__args__
_FORMS: tuple[str, ...] = ContentForm.__args__
# 시작일만 있으면 그날 하루로 보는 종류(출시일, 점검). 이벤트·테스트·할인은 시작 뒤 끝났는지 알 수 없다
SINGLE_DAY_KINDS = frozenset({"RELEASE", "MAINTENANCE"})

# 순서가 중요하다(값 → 일정 → 신규 콘텐츠 → 요약): "피해량은 언제 바뀌었나"는 값, "다음 DLC 언제 나와?"는 일정,
# "새로 추가된 콘텐츠는?"은 신규 콘텐츠, "바뀐 점"은 요약
_VALUE_WORDS = re.compile(
    # "바뀐 버전": "Siege 모드의 최대 인원이 바뀐 버전을 모두 쓰세요"도 값의 변경 기록으로 답한다(v7)
    r"얼마|몇|수치|피해량|데미지|대미지|쿨다운|재사용|가격|확률|체력|공격력|방어력|바뀐\s*버전|damage|cooldown|price",
    re.IGNORECASE
)
_SUMMARY_WORDS = re.compile(
    # "패치노트"만으로는 요약 질문이 아니다("2.4.1 패치노트의 알려진 문제는?" 같은 출처 지칭)
    r"바뀐\s*(점|것|내용)|변경\s*(사항|점|내용)|변경점|(패치|업데이트)\s*내용|요약|달라진|"
    r"새로운\s*(점|것)|(뭐|무엇)(가|이)\s*(바뀌|달라)|추가된\s*(기능|것|점)|고친\s*(버그|것)",
    re.IGNORECASE,
)
_SCHEDULE_WORDS = re.compile(r"언제|기간|일정|점검|시작|종료|마감|까지|출시일")
_CONTENT_WORDS = re.compile(
    # 한글도 단어 글자라 "DLC에는"에서 \b가 성립하지 않는다 → 영문자 경계만 본다
    r"콘텐츠|컨텐츠|(?<![a-z])DLC(?![a-z])|확장\s*팩|확장판|expansion|"
    r"(신규|새로운|새)\s*(맵|캐릭터|지역|모드|보스|무기|아이템|시즌|영웅|요원|레전드)",
    re.IGNORECASE,
)


def classify(question: str) -> QaIntent:
    if _VALUE_WORDS.search(question):
        return QaIntent.VALUE
    if _SCHEDULE_WORDS.search(question):
        return QaIntent.SCHEDULE
    if _CONTENT_WORDS.search(question):
        return QaIntent.CONTENT
    if _SUMMARY_WORDS.search(question):
        return QaIntent.UPDATE_SUMMARY
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
        # v6: "이름과 수치를 그대로"를 문장 전체를 옮기라는 뜻으로 받아 영어 원문이 섞이던 문제(7DTD·DST) 대응.
        # 한국어 지시는 목록형 칸(요약·콘텐츠)에만 둔다 — 공통 지시에 두자 짧은 답의 장소명을 잘못 번역했다
        # ("north bridge" → "북쪽 다락", 재실험 Q04)
        "문서가 영어여도 구체적인 이름과 수치는 원문 그대로, 설명은 한국어 한 문장으로 쓴다(예: 'Unholy Trident 피해량 88 → 150', "
        "'멀티플레이에서 강화되지 않은 아이템에 boosted 아이콘이 뜨던 버그 수정'). "
        "'여러 버그 수정'처럼 뭉뚱그리지 않는다. 해당 내용이 없으면 빈 목록.\n"
        "문서에 요약할 업데이트가 없으면 모든 목록을 비운다."
    ),
    QaIntent.VALUE: (
        # v7: 최신 값 고르기·횟수 세기·차이 계산은 서버가 한다(value.py). 모델은 문서에 적힌 변경만 옮긴다
        "질문이 묻는 대상의 값이 문서에서 바뀌거나 정해진 기록을 모두 찾아 history에 옮겨 적는다. "
        "계산·비교·최신 값 고르기는 하지 않는다(기록만 빠짐없이).\n"
        "- target: 질문이 묻는 대상(예: 'Arc Lance 피해량')\n"
        f"- history: 최대 {MAX_HISTORY}건. 문서마다 그 대상의 값이 나오면 한 건씩\n"
        "  - doc: 그 문서의 ID(예: N012)\n"
        "  - version: 그 문서 제목·본문에 적힌 버전(적혀 있지 않으면 빈 문자열)\n"
        "  - before: 바뀌기 전 값(새로 추가됐거나 적혀 있지 않으면 빈 문자열)\n"
        "  - after: 바뀐 뒤 값 또는 그 문서에 적힌 값. 단위는 문서 그대로(예: '20초', '800ms')\n"
        "대상이 문서에 없으면 history를 비운다."
    ),
    QaIntent.SCHEDULE: (
        f"질문은 이벤트·시즌·출시·점검·테스트·할인 같은 일정을 묻는다. 질문에 맞는 일정을 최대 {MAX_SCHEDULE_ITEMS}건, "
        "날짜가 늦은 것부터 items에 쓴다. 문서에 날짜가 있는 일정만 쓰고, 없으면 items를 비운다.\n"
        "- name: 일정의 이름\n"
        "- kind: EVENT(이벤트·시즌) / RELEASE(업데이트·DLC 출시) / MAINTENANCE(점검) / TEST(베타·테스트 서버) / SALE(할인)\n"
        "- start: 시작 날짜 YYYY-MM-DD(모르면 빈 문자열). 하루짜리 일정(출시일 등)은 start에만 쓴다\n"
        "- end: 종료 날짜 YYYY-MM-DD. 문서에 종료일이 따로 적혀 있지 않으면 빈 문자열(시작일을 베끼지 않는다)\n"
        "진행 중인지·끝났는지는 판단하지 않는다(날짜만 정확히 옮긴다)."
    ),
    QaIntent.CONTENT: (
        "질문은 새로 추가됐거나 나올 콘텐츠(무료 업데이트·DLC·확장)를 묻는다. 질문이 특정 콘텐츠를 말하면 그것을, "
        "아니면 문서 중 가장 최근에 발표·출시된 콘텐츠 하나를 고른다.\n"
        "- name: 콘텐츠 이름(예: 'Silk & Silver', '1.4.5 Bigger & Boulder'). 문서에 없으면 '근거 없음'\n"
        "- form: FREE_UPDATE(무료 업데이트) / DLC / EXPANSION(확장) / OTHER\n"
        "- release_date: 출시(예정)일 YYYY-MM-DD(모르면 빈 문자열)\n"
        f"- highlights: 핵심 내용 최대 {MAX_HIGHLIGHTS}개. 이름은 원문 그대로, 설명은 한국어로 쓴다(예: '새 보스 Deerclops'). "
        "'많은 콘텐츠'처럼 뭉뚱그리지 않는다."
    ),
    QaIntent.OTHER: "- answer: 질문에 대한 짧고 구체적인 답. 문서에 없으면 '근거 없음'",
}

_STR = {"type": "string"}
_SOURCES = {"type": "array", "items": _STR, "maxItems": 5}


def _list(n: int) -> dict:
    return {"type": "array", "items": _STR, "maxItems": n}


_DATE = {"type": "string", "description": "YYYY-MM-DD or empty"}
_SCHEDULE_ITEM = {
    "type": "object",
    "properties": {"name": _STR, "kind": {"type": "string", "enum": list(_KINDS)}, "start": _DATE, "end": _DATE},
    "required": ["name", "kind", "start", "end"],
}

_VALUE_CHANGE = {
    "type": "object",
    "properties": {"doc": _STR, "version": _STR, "before": _STR, "after": _STR},
    "required": ["doc", "version", "before", "after"],
}

_SCHEMAS = {
    QaIntent.UPDATE_SUMMARY: {"version": _STR, "date": _STR, "new_features": _list(MAX_ITEMS),
                              "balance": _list(MAX_ITEMS), "bug_fixes": _list(MAX_ITEMS), "sources": _SOURCES},
    QaIntent.VALUE: {"target": _STR, "history": {"type": "array", "items": _VALUE_CHANGE, "maxItems": MAX_HISTORY},
                     "sources": _SOURCES},
    QaIntent.SCHEDULE: {"items": {"type": "array", "items": _SCHEDULE_ITEM, "maxItems": MAX_SCHEDULE_ITEMS},
                        "sources": _SOURCES},
    QaIntent.CONTENT: {"name": _STR, "form": {"type": "string", "enum": list(_FORMS)}, "release_date": _DATE,
                       "highlights": _list(MAX_HIGHLIGHTS), "sources": _SOURCES},
    QaIntent.OTHER: {"answer": _STR, "sources": _SOURCES},
}


# 날짜가 답을 가르는 유형: 오늘 날짜를 알려 주고, RAG에 최근 공지 청크를 더 넣는다(PRD v6.8)
RECENCY_INTENTS = frozenset({QaIntent.SCHEDULE, QaIntent.CONTENT})
# "다음 점검", "진행 중인 이벤트"처럼 지금·앞으로를 묻는 말
_CURRENT_WORDS = re.compile(r"다음|진행|예정|곧|앞으로|현재|지금|요즘|이번|최근|새로")


def asks_current(question: str) -> bool:
    return _CURRENT_WORDS.search(question) is not None


def system_prompt(intent: QaIntent, today: date | None = None) -> str:
    text = _COMMON + _INSTRUCTIONS[intent]
    if intent in RECENCY_INTENTS:
        # 모델이 "다음·진행 중"을 고를 기준. 진행 중·종료 판정 자체는 여전히 서버가 한다(status_of)
        text += (f"\n오늘은 {(today or today_kst()).isoformat()}이다. 질문이 다음·진행 중·예정·최근을 물으면 "
                 "오늘 이후이거나 오늘을 포함하는 일정, 가장 최근에 발표된 콘텐츠를 먼저 고른다.")
    return text


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


class ValueChange(_Loose):
    doc: str = ""
    version: str = ""
    before: str = ""
    after: str = ""
    date: str = ""  # 서버가 문서 날짜로 채운다


class ValueAnswer(_Loose):
    target: str = ""
    history: list[ValueChange] = []
    sources: list[str] = []
    # 아래는 서버가 history와 질문으로 계산한다(value.compute_value). v5·v6 기록은 모델이 value를 직접 채웠다
    kind: str = "CURRENT"
    value: str = ""
    changed_in: str = ""
    previous: str = ""
    note: str = ""  # 화면 공용 문장의 괄호 설명(예: "12 → 13")


class ScheduleItem(_Loose):
    name: str = ""
    kind: str = "EVENT"
    start: str = ""
    end: str = ""
    status: Status = Status.UNKNOWN  # 서버가 채운다

    @field_validator("kind", mode="before")
    @classmethod
    def _known_kind(cls, v: object) -> str:
        # 스키마 enum으로 강제하지만, 벗어난 값 하나 때문에 답 전체를 버리지 않는다
        return v if v in _KINDS else "EVENT"


class ScheduleAnswer(_Loose):
    items: list[ScheduleItem] = []
    sources: list[str] = []


class ContentAnswer(_Loose):
    name: str = ""
    form: str = "OTHER"
    release_date: str = ""
    highlights: list[str] = []
    status: Status = Status.UNKNOWN  # 서버가 채운다
    sources: list[str] = []

    @field_validator("form", mode="before")
    @classmethod
    def _known_form(cls, v: object) -> str:
        return v if v in _FORMS else "OTHER"


class OtherAnswer(_Loose):
    answer: str = ""
    sources: list[str] = []


_MODELS: dict[QaIntent, type[_Loose]] = {
    QaIntent.UPDATE_SUMMARY: UpdateSummary,
    QaIntent.VALUE: ValueAnswer,
    QaIntent.SCHEDULE: ScheduleAnswer,
    QaIntent.CONTENT: ContentAnswer,
    QaIntent.OTHER: OtherAnswer,
}

Filled = UpdateSummary | ValueAnswer | ScheduleAnswer | ContentAnswer | OtherAnswer

_YMD = re.compile(r"(\d{4})[-./]\s*(\d{1,2})[-./]\s*(\d{1,2})")
# 진행 중·예정을 먼저, 끝난 일정은 마지막에
_STATUS_ORDER = {Status.ONGOING: 0, Status.UPCOMING: 1, Status.UNKNOWN: 2, Status.ENDED: 3}


def today_kst() -> date:
    return datetime.now(KST).date()


def parse_day(text: str) -> date | None:
    """"2026-08-31", "2026-08-31T19:00:00", "2026. 8. 31." → 날짜. 못 읽으면 None(시각·시간대는 버린다)."""
    m = _YMD.search(text)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def status_of(start: str, end: str, today: date, single_day: bool = False) -> Status:
    """날짜 단위 비교. 종료만 있으면 그날까지 진행 중으로 본다.
    시작만 있을 때: 출시일 같은 하루짜리(single_day)는 그날 진행 중·지나면 종료, 이벤트처럼 기간이 있는 일정은
    시작 뒤 끝났는지 알 수 없어 UNKNOWN(Apex "Blood Pact Event" 시작일만 있는데 종료로 판정하던 문제)."""
    s, e = parse_day(start), parse_day(end)
    if s is None and e is None:
        return Status.UNKNOWN
    if s is not None and today < s:
        return Status.UPCOMING
    if e is None and not single_day:
        return Status.UNKNOWN
    last = e or s
    return Status.ENDED if today > last else Status.ONGOING


def _clean(text: str, titles: dict[str, str]) -> str:
    text = text.strip()
    # 칸 전체가 문서 번호뿐이면(예: 버전을 묻는데 "[N122]") 그 공지 제목으로 바꾼다 — 지우면 빈 답이 된다
    only_ids = _DOC_ID.findall(text)
    if only_ids and not _DOC_ID.sub("", text).strip(" ,[]()"):
        return ", ".join(titles.get(i, "") for i in only_ids).strip(", ")[:MAX_FIELD_CHARS]
    return _BRACKETED_ID.sub("", text).strip()[:MAX_FIELD_CHARS]


# 모델이 "N115"를 "N0115"처럼 0을 더 붙여 적기도 한다(v7 재실험에서 값 기록이 통째로 버려진 원인)
_LOOSE_DOC_ID = re.compile(r"\bN0*(\d{1,3})\b")


def doc_ids(text: str) -> list[str]:
    """글 속 문서 ID를 정규형(N + 세 자리)으로. 순서 유지, 중복 제거."""
    return list(dict.fromkeys(f"N{int(n):03d}" for n in _LOOSE_DOC_ID.findall(text)))


def _is_refusal(text: str) -> bool:
    return not text or any(p in text for p in REFUSALS)


_LIST_LIMITS = {"highlights": MAX_HIGHLIGHTS}
_ENUM_KEYS = {"kind", "form", "status"}
# 모델에 요구하지 않고 서버가 채우는 칸(스키마 required에서 뺀다)
SERVER_FIELDS = frozenset({"status", "kind", "value", "changed_in", "previous", "note"})  # 값 기록 안의 date도 서버가 채운다


def _clean_fields(data: dict, titles: dict[str, str]) -> dict:
    out = {}
    for key, val in data.items():
        if key == "sources":
            out[key] = list(dict.fromkeys(i for s in val for i in doc_ids(s)))
        elif key in _ENUM_KEYS:
            out[key] = val
        elif key == "doc":  # 문서 ID 칸은 제목으로 바꾸지 않는다
            ids = doc_ids(val)
            out[key] = ids[0] if ids else ""
        elif isinstance(val, list) and val and isinstance(val[0], dict):  # 일정 items, 값 history
            out[key] = [_clean_fields(v, titles) for v in val]
        elif isinstance(val, list):
            out[key] = [c for v in val if (c := _clean(v, titles))][:_LIST_LIMITS.get(key, MAX_ITEMS)]
        else:
            out[key] = _clean(val, titles)
    return out


def parse(intent: QaIntent, content: str, titles: dict[str, str] | None = None,
          today: date | None = None) -> Filled | None:
    """모델 JSON을 유형별 칸으로. titles = 문서 ID → 제목, today = 상태 판정 기준(기본 오늘 한국 날짜).
    형식이 깨졌으면(출력 한도에서 잘림 등) None."""
    titles = titles or {}
    try:
        raw = json.loads(content.rsplit("</think>", 1)[-1])
        filled = _MODELS[intent].model_validate(raw)
    except (ValueError, ValidationError):
        return None
    filled = _MODELS[intent].model_validate(_clean_fields(filled.model_dump(), titles))
    today = today or today_kst()
    if isinstance(filled, ScheduleAnswer):
        items = [i.model_copy(update={"status": status_of(i.start, i.end, today, i.kind in SINGLE_DAY_KINDS)})
                 for i in filled.items if not _is_refusal(i.name) and (i.start or i.end)]
        items.sort(key=lambda i: _STATUS_ORDER[i.status])  # 안정 정렬: 같은 상태끼리는 모델 순서
        filled = filled.model_copy(update={"items": items[:MAX_SCHEDULE_ITEMS]})
    elif isinstance(filled, ContentAnswer):
        filled = filled.model_copy(update={"status": status_of(filled.release_date, "", today, single_day=True)})
    return filled


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
        if filled.note:
            return f"{filled.value} ({filled.note})", False
        detail = ""
        if filled.changed_in and filled.previous:
            detail = f" ({filled.changed_in}에서 {filled.previous} → {filled.value})"
        elif filled.changed_in:
            detail = f" ({filled.changed_in})"
        return filled.value + detail, False
    if isinstance(filled, ScheduleAnswer):
        if not filled.items:
            return REFUSAL, True
        return "\n".join(f"{i.name}: {_period(i.start, i.end, i.kind in SINGLE_DAY_KINDS)} ({_STATUS_KO[i.status]})" for i in filled.items), False
    if isinstance(filled, ContentAnswer):
        if _is_refusal(filled.name) or not (filled.highlights or filled.release_date):
            return REFUSAL, True
        head = filled.name + (f" ({filled.release_date})" if filled.release_date else "")
        return "\n".join([head] + [f"- {h}" for h in filled.highlights]), False
    if _is_refusal(filled.answer):
        return REFUSAL, True
    return filled.answer, False


_STATUS_KO = {Status.ONGOING: "진행 중", Status.UPCOMING: "예정", Status.ENDED: "종료", Status.UNKNOWN: "상태 모름"}


def _period(start: str, end: str, single_day: bool) -> str:
    if start and end:
        return f"{start} ~ {end}"
    if end:
        return f"~ {end}"
    return start if single_day else f"{start}부터"  # 이벤트 등은 시작일만 알려진 것
