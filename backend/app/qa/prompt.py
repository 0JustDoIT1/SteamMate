"""뉴스 질문 입력 구성(문서 표시·최신 업데이트 판별)과 자유 형식 응답 해석. 7단계 실험과 서비스 공용.

지시문·답변 틀은 templates.py(v6). "답: / 근거:" 해석 함수는 v1~v4 실험 결과를 다시 채점할 때 쓴다.
"""

import re

DOC_SEPARATOR = "\n\n---\n\n"
LATEST_MARK = "(최신 업데이트)"
_DOC_ID = re.compile(r"\bN\d{3}\b")
_ANSWER = re.compile(r"\s*\**\s*답\s*\**\s*[:：]\s*(.*)")
_SOURCES = re.compile(r"\s*\**\s*근거\s*\**\s*[:：]")
# 패치 공지로 보는 제목: 버전 번호(1.4.5.7, 2.3) 또는 업데이트·패치·핫픽스
_PATCH_TITLE = re.compile(r"\b\d+(?:\.\d+){1,3}\b|update|patch|hotfix|업데이트|패치|핫픽스", re.IGNORECASE)
# 본문 속 구분선(---, ===)은 문서 구분자와 헷갈리므로 지운다
_RULE_LINE = re.compile(r"^[ \t]*[-=_*]{3,}[ \t]*$", re.MULTILINE)


# 패치처럼 보여도 업데이트가 아닌 글: 상점 개편("Store Update 2.4.0"), 트위치 드롭, 굿즈(PRD v6.8, 24개 게임 조사)
_NOT_UPDATE_TITLE = re.compile(
    r"\b(store|shop|drops?|merch|plush(ie)?s?|figure|figuarts|statue|keycap|hoodie|vinyl|replicas?|sweepstakes|"
    r"giveaway)\b|굿즈|상점",
    re.IGNORECASE,
)
# 정식이 아닌 테스트 빌드: 7DTD "V3.4.0 EXP", DbD "PTB", Factorio "Experimental", "Open Beta"
_TEST_TITLE = re.compile(r"\b(exp|experimental|ptb|beta|public test)\b|베타|테스트 서버", re.IGNORECASE)
_REPORT_TITLE = re.compile(r"\breport\b", re.IGNORECASE)
_HOTFIX_TITLE = re.compile(r"hot\s*i?fix|bug\s*fix|핫픽스", re.IGNORECASE)
_MAJOR_TITLE = re.compile(r"expansion|major update|대형 업데이트|확장팩", re.IGNORECASE)
# 끝자리가 모두 0인 버전(2.0, 1.20.0, 3.4.0.0)은 대형 업데이트로 본다. 1.4.5.7·2.4.1은 패치
_VERSION = re.compile(r"(?<![\d.])v?(\d+)\.(\d+)((?:\.\d+){0,2})(?![\w.])", re.IGNORECASE)  # "7.41f"는 버전으로 보지 않음


# "Update"가 들어가도 패치가 아닌 소식 글(버전 번호가 없을 때만): PUBG "[Dev Letter] Anti-Cheat Update" 등.
# 소식 화면의 규모 표시에만 쓴다 — 최신 업데이트 판정(latest_update_id)에 넣으면 실험 결과가 달라져 재실험이 필요하다
_NEWS_NOT_PATCH = re.compile(
    r"dev(eloper)?\s*(letter|diary|update)|community\s*(update|event)|roadmap|anti-?cheat|state of the game|"
    r"q\s*&\s*a|weekly bans|ban notice",
    re.IGNORECASE,
)


def is_patch_title(title: str) -> bool:
    """패치·업데이트 공지 꼴 제목인가(버전 번호·업데이트·패치·핫픽스, 상점·드롭·굿즈 글과 버전 없는 소식 글 제외)."""
    if _PATCH_TITLE.search(title) is None or _NOT_UPDATE_TITLE.search(title) is not None:
        return False
    return _VERSION.search(title) is not None or _NEWS_NOT_PATCH.search(title) is None


# 상점·드롭·굿즈를 묻는 질문(이때만 일정 답에 상점 글을 남긴다)
_STORE_QUESTION = re.compile(r"상점|스토어|굿즈|드롭|\b(store|shop|drops?)\b", re.IGNORECASE)


def is_store_title(title: str) -> bool:
    """상점 개편·드롭·굿즈 글("November Store Update 2026")인가."""
    return _NOT_UPDATE_TITLE.search(title) is not None


def asks_store(question: str) -> bool:
    return _STORE_QUESTION.search(question) is not None


def is_test_build(title: str) -> bool:
    return _TEST_TITLE.search(title) is not None


def title_version(title: str) -> str:
    """제목 속 버전 번호("Update 1.20.1.2" → "1.20.1.2", "V3.4.0 Stable" → "3.4.0"). 없으면 빈 문자열.
    모델이 요약의 버전 칸을 비웠을 때 채운다."""
    m = _VERSION.search(title)
    return f"{m[1]}.{m[2]}{m[3]}" if m else ""


def update_scale(title: str) -> str:
    """공지 제목으로 어림한 규모: HOTFIX / MAJOR / PATCH. 제목 관례가 게임마다 달라 어림값이다."""
    if _HOTFIX_TITLE.search(title):
        return "HOTFIX"
    if _MAJOR_TITLE.search(title):
        return "MAJOR"
    m = _VERSION.search(title)
    if m and all(part == "0" for part in m[3].split(".")[1:]):
        return "MAJOR"
    return "PATCH"


def recent_ids(docs: list[tuple[str, str]], n: int) -> list[str]:
    """(문서 ID, 제목) 목록(오래된 글부터)에서 상점·굿즈 글을 뺀 최근 n건(최신 먼저). 일정·콘텐츠 질문의 RAG에
    각 글의 청크를 더 넣는다 — 의미 검색은 날짜를 보지 않아 옛 이벤트·DLC가 걸리던 문제 대응(PRD v6.8).
    핫픽스 글도 뺀다 — 일정·새 콘텐츠 소식이 거의 없는데, DST처럼 최근 5건이 모두 핫픽스면 그 바로 앞의
    "Hallowed Nights Returns!" 이벤트 공지가 밀려나 "진행 중인 이벤트"를 못 찾았다(2026-11-07)."""
    return [i for i, t in reversed(docs) if not _NOT_UPDATE_TITLE.search(t) and not _HOTFIX_TITLE.search(t)][:n]


def latest_update_id(docs: list[tuple[str, str]]) -> str | None:
    """(문서 ID, 제목) 목록(오래된 글부터)에서 가장 최근 정식 패치 공지. 정식이 없으면 테스트 빌드 공지,
    그것도 없으면 상점·굿즈 글이 아닌 가장 최근 글, 그것도 없으면 가장 최근 글."""
    if not docs:
        return None
    candidates = [(i, t) for i, t in reversed(docs) if not _NOT_UPDATE_TITLE.search(t)]
    # "Map Service Report - Update 44.1"(맵 순환 안내)은 같은 날 "Patch Notes - Update 44.1"보다 몇 분 늦게 올라와
    # 최신 업데이트로 뽑혔다(PUBG, 2026-11-07) — 보고 글은 패치 공지 후보에서 뺀다
    patches = [(i, t) for i, t in candidates if _PATCH_TITLE.search(t) and not _REPORT_TITLE.search(t)]
    for doc_id, title in patches:
        if not is_test_build(title):
            return doc_id
    if patches:
        return patches[0][0]
    return candidates[0][0] if candidates else docs[-1][0]


def mark_latest(title: str) -> str:
    return f"{LATEST_MARK} {title}"


def strip_rules(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", _RULE_LINE.sub("", text)).strip()


def doc_header(doc_id: str, title: str, date: str) -> str:
    return f"[{doc_id}] {title} ({date})"


def user_prompt(context: str, question: str) -> str:
    return f"문서:\n{context}\n\n질문: {question}"


def final_text(content: str) -> str:
    """Thinking 모델의 추론 부분(</think> 앞)을 버린다."""
    return content.rsplit("</think>", 1)[-1].strip()


def answer_line(text: str) -> str | None:
    """"답:" 뒤부터 "근거:" 줄 전까지(여러 줄 포함). "답:" 줄이 없으면 None."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _ANSWER.match(line)
        if m:
            block = [m.group(1)]
            for rest in lines[i + 1:]:
                if _SOURCES.match(rest):
                    break
                block.append(rest)
            return "\n".join(block).strip()
    return None


def cited_ids(text: str) -> list[str]:
    """"근거:" 줄의 문서 ID. 그 줄이 없으면 본문 전체에서 찾는다."""
    for line in text.splitlines():
        if _SOURCES.match(line):
            return list(dict.fromkeys(_DOC_ID.findall(line)))
    return list(dict.fromkeys(_DOC_ID.findall(text)))
