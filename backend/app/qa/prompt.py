"""뉴스 질문 입력 구성(문서 표시·최신 업데이트 판별)과 자유 형식 응답 해석. 7단계 실험과 서비스 공용.

지시문·답변 틀은 templates.py(v5). "답: / 근거:" 해석 함수는 v1~v4 실험 결과를 다시 채점할 때 쓴다.
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


def latest_update_id(docs: list[tuple[str, str]]) -> str | None:
    """(문서 ID, 제목) 목록(오래된 글부터)에서 가장 최근 패치 공지. 없으면 가장 최근 글."""
    for doc_id, title in reversed(docs):
        if _PATCH_TITLE.search(title):
            return doc_id
    return docs[-1][0] if docs else None


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
