"""영어로 남은 목록 항목만 다시 번역(PRD v6.10).

공지 원문이 영어라 긴 문장은 모델이 번역하지 않고 그대로 옮긴다(DST·7DTD). 답을 만드는 지시문에 한국어를 강하게
요구하면 짧은 답의 이름까지 오역해 정확도가 떨어졌다("north bridge" → "북쪽 다락", 재실험 Q04). 그래서 답은 그대로
두고, 한글이 거의 없는 줄만 번역만 하는 요청을 한 번 더 보낸다.
- 이름 보호: 원문에서 대문자로 시작하는 이름(아이템·장소·캐릭터)과 숫자가 번역에 그대로 있는지 서버가 확인하고,
  아니면 그 줄은 원문을 보인다. 최악의 경우가 지금처럼 영어로 보이는 것이다.
- 영어 줄이 없으면 호출하지 않는다. 번역 요청이 실패해도 답은 그대로 낸다.
"""

import json
import logging
import re

from app.errors import AppError
from app.qa.llm import LlmClient

logger = logging.getLogger(__name__)

_HANGUL = re.compile(r"[가-힣]")
_LATIN = re.compile(r"[A-Za-z]")
# 대문자로 시작하는 단어가 이어진 덩어리(예: "Shadow Fire", "Scout's Sling")
_NAME_RUN = re.compile(r"[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*)*")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_POSSESSIVE = re.compile(r"['’]s$")

SYSTEM = (
    "너는 게임 패치 노트 번역가다. 주어진 영어 문장들을 자연스럽고 짧은 한국어로 옮긴다.\n"
    "- 대문자로 시작하는 이름(아이템·장소·캐릭터·기능·모드 이름)과 숫자·단위는 원문 철자 그대로 둔다"
    "(예: 'Willow's Shadow Fire sometimes circles its target' → 'Willow의 Shadow Fire가 가끔 대상 주위를 맴돎').\n"
    "- 문장 수와 순서를 그대로 지키고, 내용을 더하거나 빼지 않는다."
)


def needs_translation(text: str) -> bool:
    """한글이 거의 없는 영어 문장인가(한글 글자가 영문 글자의 20% 미만이고 영문이 15자 이상)."""
    latin = len(_LATIN.findall(text))
    return latin >= 15 and len(_HANGUL.findall(text)) < latin * 0.2


def protected_words(text: str) -> set[str]:
    """번역 뒤에도 그대로 있어야 할 이름 단어. 문장 첫 단어는 이름이 아니어도 대문자라("Fixed", "Players") 뺀다.
    소유격("Willow's" → "Willow")은 번역에서 "Willow의"가 되므로 's를 떼고 본다."""
    words: set[str] = set()
    for m in _NAME_RUN.finditer(text):
        parts = m[0].split()
        if m.start() == len(text) - len(text.lstrip()):  # 문장 첫 덩어리는 첫 단어를 뺀다
            parts = parts[1:]
        words.update(w for p in parts if len(w := _POSSESSIVE.sub("", p).strip("'’-")) >= 2)
    return words


def _keeps_names_and_numbers(original: str, translated: str) -> bool:
    if not _HANGUL.search(translated):
        return False
    if any(w not in translated for w in protected_words(original)):
        return False
    return all(n in translated for n in _NUMBER.findall(original))


def _schema(n: int) -> dict:
    items = {"type": "array", "items": {"type": "string"}, "minItems": n, "maxItems": n}
    return {"type": "object", "properties": {"translations": items}, "required": ["translations"]}


async def translate_lines(llm: LlmClient, lines: list[str], num_ctx: int) -> list[str]:
    """lines 중 영어 줄만 번역한 목록(같은 길이·순서). 확인을 통과하지 못한 줄과 실패한 요청은 원문 그대로.

    num_ctx는 답변 요청과 같게 준다 — 다르면 Ollama가 모델을 다시 올려 다음 질문까지 10초 가까이 느려졌다."""
    targets = [i for i, line in enumerate(lines) if needs_translation(line)]
    if not targets:
        return lines
    user = json.dumps({"sentences": [lines[i] for i in targets]}, ensure_ascii=False)
    try:
        result = await llm.chat(SYSTEM, user, num_ctx, _schema(len(targets)))
        translations = json.loads(result.content.rsplit("</think>", 1)[-1])["translations"]
    except (AppError, ValueError, KeyError, TypeError) as exc:
        logger.warning("translation skipped: %s", type(exc).__name__)
        return lines
    if not isinstance(translations, list) or len(translations) != len(targets):
        logger.warning("translation count mismatch: %s", len(targets))
        return lines
    out = list(lines)
    kept = 0
    for i, translated in zip(targets, translations, strict=True):
        if isinstance(translated, str) and _keeps_names_and_numbers(lines[i], translated.strip()):
            out[i] = translated.strip()
        else:
            kept += 1
    if kept:
        logger.info("translation rejected for %s of %s lines (names or numbers changed)", kept, len(targets))
    return out
