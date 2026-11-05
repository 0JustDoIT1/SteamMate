"""영어로 남은 목록 항목 재번역(PRD v6.10): 대상 고르기, 이름·숫자 보호, 실패 시 원문."""

import json

import pytest

from app.errors import AppError, ErrorCode
from app.qa.llm import ChatResult
from app.qa.translate import needs_translation, protected_words, translate_lines

WILLOW = "Willow's Shadow Fire sometimes circles around its target without reaching it."
PIGS = "Frankenswine, Mermummy, and Vamphare no longer share targets when aggroed individually."
POTION = "Super Mana Potion now restores 400 mana instead of 300."
KOREAN = "멀티플레이에서 강화되지 않은 아이템에 'boosted' 아이콘이 뜨던 버그 수정"


class FakeTranslator:
    model = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.calls: list[tuple[str, str, dict | None]] = []

    async def chat(self, system, user, num_ctx, schema=None):
        self.calls.append((system, user, schema))
        if isinstance(self.reply, Exception):
            raise self.reply
        return ChatResult(json.dumps({"translations": self.reply}, ensure_ascii=False), 50, "stop")

    async def embed(self, texts):
        raise AssertionError("번역에는 임베딩을 쓰지 않는다")


@pytest.mark.parametrize(("text", "expected"), [
    (WILLOW, True),
    (KOREAN, False),  # 이름 몇 개가 섞인 한국어 문장은 그대로
    ("Scout's Sling 추가", False),
    ("Hotfix", False),  # 짧은 이름만 있는 줄
])
def test_needs_translation(text, expected):
    assert needs_translation(text) is expected


def test_protected_words_skip_sentence_start_and_possessive():
    # 문장 첫 단어("Willow's")는 이름이어도 빼고, 나머지 이름 단어를 지킨다
    assert protected_words(WILLOW) == {"Shadow", "Fire"}
    assert protected_words("Fixed a bug where Glass Canyon spawns were exploitable") == {"Glass", "Canyon"}
    assert protected_words(PIGS) == {"Mermummy", "Vamphare"}


async def test_translates_only_english_lines_and_keeps_order():
    llm = FakeTranslator(["Willow의 Shadow Fire가 대상에 닿지 못하고 주위를 맴도는 버그 수정",
                          "Super Mana Potion 마나 회복량 300 → 400"])
    out = await translate_lines(llm, [WILLOW, KOREAN, POTION], 12288)
    assert out == ["Willow의 Shadow Fire가 대상에 닿지 못하고 주위를 맴도는 버그 수정", KOREAN,
                   "Super Mana Potion 마나 회복량 300 → 400"]
    _, user, schema = llm.calls[0]
    assert json.loads(user) == {"sentences": [WILLOW, POTION]}  # 한국어 줄은 보내지 않는다
    assert schema["properties"]["translations"]["minItems"] == 2


@pytest.mark.parametrize("bad", [
    "윌로우의 그림자 불꽃이 대상 주위를 맴도는 버그 수정",  # 이름을 번역해 버림
    "Willow's Shadow Fire sometimes circles around its target.",  # 한글이 없음
])
async def test_rejects_translation_that_changes_names(bad):
    assert await translate_lines(FakeTranslator([bad]), [WILLOW], 12288) == [WILLOW]


async def test_rejects_translation_that_drops_numbers():
    out = await translate_lines(FakeTranslator(["Super Mana Potion 마나 회복량 증가"]), [POTION], 12288)
    assert out == [POTION]


async def test_no_call_when_nothing_to_translate():
    llm = FakeTranslator([])
    assert await translate_lines(llm, [KOREAN, "Scout's Sling 추가"], 12288) == [KOREAN, "Scout's Sling 추가"]
    assert llm.calls == []


@pytest.mark.parametrize("reply", [
    AppError(ErrorCode.AI_UNAVAILABLE, "down", 503),  # 번역 요청이 실패해도 답은 원문으로 낸다
    ["하나만"],  # 개수가 다름(스키마로 강제하지만 확인한다)
])
async def test_failures_keep_original(reply):
    assert await translate_lines(FakeTranslator(reply), [WILLOW, POTION], 12288) == [WILLOW, POTION]
