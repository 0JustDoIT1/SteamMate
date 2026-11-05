"""값 질문의 서버 계산(PRD v6.9, 지시문 v7). 7단계 실험 채점과 서비스 공용.

모델은 문서에 적힌 변경 기록(history)만 옮기고, 어느 기록을 답으로 볼지·몇 번 바뀌었는지·얼마나 달라졌는지는
여기서 정한다. 9B 모델이 여러 문서의 날짜 비교·세기·빼기를 틀리던 문제(합성 실험 latest 62%, multi 12%) 대응.
계산 방식은 질문 단어 규칙으로 고른다(예측 가능·테스트 가능). 계산할 수 없으면 지어내지 않고 근거 없음.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from app.qa.prompt import title_version
from app.qa.templates import REFUSAL, ValueAnswer, ValueChange


class ValueKind(StrEnum):
    CURRENT = "CURRENT"  # 지금 값: 날짜가 가장 늦은 기록
    AT_VERSION = "AT_VERSION"  # 질문이 말한 버전의 기록
    FIRST = "FIRST"  # 처음(출시 당시) 값
    WHEN = "WHEN"  # 언제·몇 버전에서 바뀌었나(답이 버전)
    COUNT = "COUNT"  # 몇 번 바뀌었나
    DIFF = "DIFF"  # 처음보다 얼마나 늘었나·줄었나
    VERSIONS = "VERSIONS"  # 바뀐 버전 모두


@dataclass(frozen=True)
class DocInfo:
    date: str  # YYYY-MM-DD
    title: str


# 순서가 중요하다: "2.3.0 이전에서 최신까지 몇 번"은 버전 번호가 있어도 횟수, "몇 버전에서 추가"는 버전 묻기
_COUNT = re.compile(r"몇\s*(번|차례|회)|횟수")
_DIFF = re.compile(r"얼마나\s*(늘|줄|증가|감소|올|내|커|작|높|낮|바뀌|변)|차이")
_VERSIONS = re.compile(r"(바뀐|변경된|조정된)\s*버전.*(모두|전부|다\s)|버전을\s*(모두|전부)|모든\s*버전")
_WHEN = re.compile(r"언제|(몇|어느|어떤|무슨)\s*버전")
_FIRST = re.compile(r"출시\s*당시|처음|최초|원래|초기|추가될\s*때|나왔을\s*때|추가되었|추가됐|추가된")
_VERSION_IN_Q = re.compile(r"(?<![\d.])\d+\.\d+(?:\.\d+){0,2}(?![\d.])")
_HOTFIX = re.compile(r"hot\s*i?fix|핫픽스", re.IGNORECASE)
_NOT_HOTFIX = re.compile(r"핫픽스가\s*아닌|정규")
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def value_kind(question: str) -> ValueKind:
    if _COUNT.search(question):
        return ValueKind.COUNT
    if _DIFF.search(question):
        return ValueKind.DIFF
    if _VERSIONS.search(question):
        return ValueKind.VERSIONS
    if _WHEN.search(question):
        return ValueKind.WHEN
    if _FIRST.search(question):
        return ValueKind.FIRST
    if _VERSION_IN_Q.search(question):
        return ValueKind.AT_VERSION
    return ValueKind.CURRENT


def _number(text: str) -> float | None:
    m = _NUMBER.search(text)
    return float(m[0].replace(",", "")) if m else None


def _fmt(n: float) -> str:
    return str(int(n)) if n == int(n) else f"{n:g}"


def _refused(filled: ValueAnswer, kind: ValueKind, history: list[ValueChange]) -> ValueAnswer:
    return filled.model_copy(update={"kind": kind, "value": REFUSAL, "history": history, "changed_in": "",
                                     "previous": "", "note": "", "sources": []})


def _docs_of(history: list[ValueChange]) -> list[str]:
    return list(dict.fromkeys(h.doc for h in history))


def _pick_version(question: str, history: list[ValueChange], docs: dict[str, DocInfo]) -> ValueChange | None:
    """질문 속 버전과 같은 기록. 같은 버전의 정규 패치·핫픽스가 둘 다 있으면 질문이 핫픽스를 말할 때만 핫픽스."""
    wanted = _VERSION_IN_Q.search(question)[0]
    matches = [h for h in history if h.version == wanted]
    if not matches:
        return None
    wants_hotfix = _HOTFIX.search(question) is not None and _NOT_HOTFIX.search(question) is None
    preferred = [h for h in matches if (_HOTFIX.search(docs[h.doc].title) is not None) == wants_hotfix]
    return (preferred or matches)[-1]


def compute_value(filled: ValueAnswer, question: str, docs: dict[str, DocInfo],
                  allowed: set[str] | None = None) -> ValueAnswer:
    """history 정리(넘긴 문서만, 날짜순, 빈 버전은 제목에서) → 질문 꼴에 맞춰 value·changed_in·previous·note 계산.
    출처는 답으로 고른 기록의 문서(횟수·차이·버전 목록은 기록 전체의 문서)로 바꾼다.

    v5·v6 기록처럼 history 없이 value가 있으면(모델이 직접 답한 옛 형식) 그대로 둔다.
    """
    if not filled.history and filled.value:
        return filled
    kind = value_kind(question)
    order = {doc_id: i for i, doc_id in enumerate(sorted(docs, key=lambda d: (docs[d].date, d)))}
    history = [
        h.model_copy(update={"date": docs[h.doc].date,
                             # 제목의 버전이 먼저: 모델은 지시문 예시 버전을 베끼기도 했다(Terraria에 "2.4.1")
                             "version": title_version(docs[h.doc].title) or h.version.lstrip("vV")})
        for h in filled.history
        if h.doc in docs and (allowed is None or h.doc in allowed) and h.after
    ]
    # 같은 기록을 두 번 적은 경우(pydantic 모델은 해시가 없어 칸 묶음으로 비교)
    history = list({(h.doc, h.version, h.before, h.after): h for h in history}.values())
    history.sort(key=lambda h: order[h.doc])  # 안정 정렬: 같은 문서 안에서는 모델 순서
    if not history:
        return _refused(filled, kind, [])

    if kind is ValueKind.COUNT:
        # 처음 기록이 "새로 추가"(이전 값 없음)면 바뀐 것으로 세지 않는다
        changes = [h for i, h in enumerate(history) if h.before != h.after and not (i == 0 and not h.before)]
        value, note = str(len(changes)), ", ".join(h.version or h.date for h in changes)
        return filled.model_copy(update={"kind": kind, "value": value, "history": history, "changed_in": "",
                                         "previous": "", "note": note, "sources": _docs_of(history)})
    if kind is ValueKind.VERSIONS:
        versions = list(dict.fromkeys(h.version or h.date for h in history))
        return filled.model_copy(update={"kind": kind, "value": ", ".join(versions), "history": history,
                                         "changed_in": "", "previous": "", "note": "", "sources": _docs_of(history)})
    if kind is ValueKind.DIFF:
        # 기준(처음 값): 첫 기록의 이전 값, 없으면(새로 추가) 그 기록의 값. 기록이 하나뿐이고 이전 값도 없으면
        # 비교할 기준이 없다 — "0, 변화 없음"으로 답하지 않는다(Terraria 마나 포션)
        if len(history) == 1 and not history[0].before:
            return _refused(filled, kind, history)
        first_raw = history[0].before or history[0].after
        first, last = _number(first_raw), _number(history[-1].after)
        if first is None or last is None:
            return _refused(filled, kind, history)
        diff = last - first
        direction = "늘어남" if diff > 0 else "줄어듦" if diff < 0 else "변화 없음"
        return filled.model_copy(update={"kind": kind, "value": _fmt(abs(diff)), "history": history,
                                         "changed_in": "", "previous": first_raw,
                                         "note": f"{direction}: {first_raw} → {history[-1].after}",
                                         "sources": _docs_of(history)})

    if kind is ValueKind.AT_VERSION:
        chosen = _pick_version(question, history, docs)
        if chosen is None:
            return _refused(filled, kind, history)
        value = chosen.after
    elif kind is ValueKind.FIRST:
        chosen = history[0]
        value = chosen.before or chosen.after
    elif kind is ValueKind.WHEN:
        # "몇 버전에서 추가됐나"는 처음 기록, "언제 바뀌었나"는 마지막 기록
        chosen = history[0] if _FIRST.search(question) else history[-1]
        value = chosen.version or chosen.date
        return filled.model_copy(update={"kind": kind, "value": value, "history": history, "changed_in": "",
                                         "previous": "", "note": f"{chosen.before or '추가'} → {chosen.after}",
                                         "sources": [chosen.doc]})
    else:
        chosen = history[-1]
        value = chosen.after
    return filled.model_copy(update={"kind": kind, "value": value, "history": history,
                                     "changed_in": chosen.version or chosen.date, "previous": chosen.before,
                                     "note": "", "sources": [chosen.doc]})
