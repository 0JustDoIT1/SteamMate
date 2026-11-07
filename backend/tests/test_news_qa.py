"""뉴스 AI 질문(F6 R2): 기능 플래그, 모드 선택, 근거 검증, 날짜 범위, LLM 장애, 캐시·직렬화, 로그 비노출."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx
import pytest

from app.config import get_settings
from app.qa.llm import ChatResult, OllamaLlm
from app.qa.templates import QaIntent, system_prompt
from tests.test_news import item, news_handler

APPID = 105600
OLD, NEW = 1793200000, 1793300000
OLD_DAY, NEW_DAY = (datetime.fromtimestamp(t, UTC).date().isoformat() for t in (OLD, NEW))
SECRET = "SECRET-BODY-MARKER"


def value_reply(value: str, sources: list[str], target: str = "Arc Lance 피해량") -> dict:
    """v7 값 칸: 모델은 변경 기록만 옮긴다. value가 근거 없음이면 기록 없음."""
    history = [] if value == "근거 없음" else [{"doc": sources[0], "version": "", "before": "", "after": value}]
    return {"target": target, "history": history, "sources": sources}


class FakeLlm:
    model = "fake-model"

    def __init__(self, reply: dict | str | None = None, prompt_tokens=None, delay: float = 0.0):
        # 기본: 값 질문("Arc Lance 피해량은?")의 JSON 칸
        self.reply = reply if reply is not None else value_reply("48", ["N002"])
        self.prompt_tokens = prompt_tokens or (lambda num_ctx: 100)
        self.delay = delay
        self.chats: list[tuple[str, str, int]] = []
        self.schemas: list[dict | None] = []
        self.embeds: list[list[str]] = []
        self.active = 0
        self.max_active = 0

    async def chat(self, system: str, user: str, num_ctx: int, schema: dict | None = None) -> ChatResult:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            self.chats.append((system, user, num_ctx))
            self.schemas.append(schema)
            # 목록이면 호출마다 차례로 답한다(답변 → 번역처럼 두 번 묻는 경우)
            reply = self.reply.pop(0) if isinstance(self.reply, list) else self.reply
            content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
            return ChatResult(content, self.prompt_tokens(num_ctx), "stop")
        finally:
            self.active -= 1

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embeds.append(texts)
        return [[1.0, 0.0] if "Arc Lance" in t else [0.0, 1.0] for t in texts]


@pytest.fixture
def fake_llm() -> FakeLlm:
    return FakeLlm()


async def _make_client(monkeypatch, steam_handler, fake_metadata, fake_prices, llm, enabled: bool):
    monkeypatch.setenv("NEWS_AI_ENABLED", "true" if enabled else "false")
    get_settings.cache_clear()
    from app.main import create_app

    external = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: steam_handler["fn"](r)))
    app = create_app(http=external, metadata=fake_metadata, prices=fake_prices, qa_llm=llm)
    return app, external


@pytest.fixture
async def ai_client(monkeypatch, steam_handler, fake_metadata, fake_prices, fake_llm) -> AsyncIterator[httpx.AsyncClient]:
    app, external = await _make_client(monkeypatch, steam_handler, fake_metadata, fake_prices, fake_llm, True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url="http://test") as ac:
        ac.app = app
        yield ac
    await external.aclose()
    get_settings.cache_clear()


def two_notes() -> list[dict]:
    return [
        item("2002", NEW, "Patch 1.1", "[p]Arc Lance: damage changed from 46 to 48.[/p]"),
        item("2001", OLD, "Patch 1.0", "[p]Arc Lance: damage changed from 42 to 46.[/p]"),
    ]


def ask(question: str = "Arc Lance 피해량은?", **extra) -> dict:
    return {"appid": APPID, "question": question, **extra}


# ---------------------------------------------------------------- 기능 플래그


async def test_disabled_by_default_without_calling_steam_or_llm(client, steam_handler):
    res = await client.post("/steam/news/ask", json=ask())  # steam_handler 기본값은 외부 호출 시 실패
    assert res.status_code == 403 and res.json()["error"]["code"] == "FEATURE_DISABLED"


async def test_news_list_reports_ask_disabled(client, steam_handler):
    steam_handler["fn"] = news_handler(two_notes())
    assert (await client.get(f"/steam/news/{APPID}")).json()["askEnabled"] is False


async def test_news_list_reports_ask_enabled(ai_client, steam_handler):
    steam_handler["fn"] = news_handler(two_notes())
    assert (await ai_client.get(f"/steam/news/{APPID}")).json()["askEnabled"] is True


async def test_server_starts_and_reports_unavailable_without_ollama(monkeypatch, steam_handler, fake_metadata, fake_prices):
    """배포 환경처럼 Ollama가 없어도 서버는 뜨고, 기능을 켠 경우에만 AI_UNAVAILABLE을 낸다."""
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1")  # 닫힌 포트
    app, external = await _make_client(monkeypatch, steam_handler, fake_metadata, fake_prices, None, True)
    assert isinstance(app.state.qa.llm, OllamaLlm)
    steam_handler["fn"] = news_handler(two_notes())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url="http://test") as ac:
        assert (await ac.get("/health")).status_code == 200
        res = await ac.post("/steam/news/ask", json=ask())
    assert res.status_code == 503 and res.json()["error"]["code"] == "AI_UNAVAILABLE"
    await app.state.qa.llm.aclose()
    await external.aclose()
    get_settings.cache_clear()


# ---------------------------------------------------------------- 답변·근거


async def test_full_context_answer_with_verified_sources(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    # 모델은 변경 기록만 옮긴다(순서도 뒤죽박죽). N999는 넘기지 않은 문서(지어낸 ID)
    fake_llm.reply = {"target": "Arc Lance 피해량", "sources": ["N002", "N999"], "history": [
        {"doc": "N002", "attribute": "Damage", "version": "", "before": "46", "after": "48"},
        {"doc": "N999", "version": "9.9", "before": "48", "after": "99"},
        {"doc": "N001", "attribute": "Damage", "version": "1.0", "before": "42", "after": "46"},
    ]}

    res = await ai_client.post("/steam/news/ask", json=ask())
    body = res.json()

    assert res.status_code == 200
    assert body["intent"] == "VALUE" and body["mode"] == "FULL_CONTEXT" and body["refused"] is False
    # 지금 값 = 서버가 날짜로 고른 마지막 기록. 버전은 제목 "Patch 1.1"에서
    assert body["answer"] == "48 (1.1에서 46 → 48)"
    assert body["value"] == {"target": "Arc Lance 피해량", "kind": "CURRENT", "value": "48", "changedIn": "1.1",
                             "previous": "46", "history": [
                                 {"attribute": "Damage", "version": "1.0", "date": OLD_DAY, "before": "42", "after": "46"},
                                 {"attribute": "Damage", "version": "1.1", "date": NEW_DAY, "before": "46", "after": "48"}]}
    assert body["summary"] is None and body["schedule"] is None and body["content"] is None
    assert [s["gid"] for s in body["sources"]] == ["2002"]  # 지어낸 ID는 버린다
    assert body["sources"][0]["url"] == f"https://store.steampowered.com/news/app/{APPID}/view/2002"
    assert body["dateRange"] == {"from": OLD_DAY, "to": NEW_DAY}
    assert body["latestUpdate"] is None  # 최신 업데이트 표시는 업데이트 요약 질문에만
    assert body["docCount"] == 2 and body["inputTokens"] == 100 and body["model"] == "fake-model"
    system, user, _ = fake_llm.chats[0]
    assert system == system_prompt(QaIntent.VALUE)
    assert fake_llm.schemas[0]["required"] == ["target", "history", "sources"]
    # 7단계 실험과 같은 형식: 오래된 글부터 N001, 입력은 최신 글이 먼저, 질문은 맨 끝
    assert user.index(f"[N002] Patch 1.1 ({NEW_DAY})") < user.index(f"[N001] Patch 1.0 ({OLD_DAY})")
    assert "(최신 업데이트)" not in user
    assert user.endswith("질문: Arc Lance 피해량은?")


async def test_update_summary_marks_latest_and_fills_sections(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.reply = {"version": "1.1", "date": NEW_DAY, "new_features": ["로드아웃 공유 [N002]"],
                      "balance": ["Arc Lance 피해량 46 → 48"], "bug_fixes": [], "sources": ["N002"]}

    body = (await ai_client.post("/steam/news/ask", json=ask("최신 업데이트에서 바뀐 점은?"))).json()

    assert body["intent"] == "UPDATE_SUMMARY" and body["refused"] is False
    assert body["latestUpdate"]["gid"] == "2002"  # 제목에 버전이 있는 가장 최근 공지
    # 규모·빌드는 공지 제목("Patch 1.1": 끝자리가 0뿐인 버전, 테스트 단어 없음)으로 서버가 정한다
    assert body["summary"] == {"version": "1.1", "date": NEW_DAY, "scale": "MAJOR", "build": "STABLE",
                               "newFeatures": ["로드아웃 공유"], "balance": ["Arc Lance 피해량 46 → 48"],
                               "bugFixes": []}
    assert body["answer"] == f"1.1 ({NEW_DAY})\n- 새 기능: 로드아웃 공유\n- 밸런스 조정: Arc Lance 피해량 46 → 48"
    assert f"[N002] (최신 업데이트) Patch 1.1 ({NEW_DAY})" in fake_llm.chats[0][1]


async def test_schedule_and_content_answers_carry_server_status(ai_client, steam_handler, fake_llm, monkeypatch):
    from app.qa import service

    monkeypatch.setattr(service, "today_kst", lambda: date(2026, 11, 5))
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.reply = {"items": [{"name": "수확 축제", "kind": "EVENT", "start": "2026-10-01", "end": "2026-10-31"},
                                {"name": "1.2 출시", "kind": "RELEASE", "start": "2026-11-20", "end": ""}],
                      "sources": ["N002"]}
    body = (await ai_client.post("/steam/news/ask", json=ask("다음 업데이트는 언제 나와?"))).json()
    assert body["intent"] == "SCHEDULE" and body["latestUpdate"] is None
    assert body["schedule"] == {"noCurrent": False, "items": [
        {"name": "1.2 출시", "kind": "RELEASE", "start": "2026-11-20", "end": "", "status": "UPCOMING", "fromPostDate": False},
        {"name": "수확 축제", "kind": "EVENT", "start": "2026-10-01", "end": "2026-10-31", "status": "ENDED",
         "fromPostDate": False}]}
    # 일정·콘텐츠 지시문에는 상태 판정과 같은 오늘(한국 날짜)이 들어간다
    assert "오늘은 2026-11-05이다" in fake_llm.chats[-1][0]

    # 지금·앞으로를 물었는데 끝난 일정만 찾으면 그렇다고 알린다(끝난 일정은 흐리게 함께)
    fake_llm.reply = {"items": [{"name": "수확 축제", "kind": "EVENT", "start": "2026-10-01", "end": "2026-10-31"}],
                      "sources": ["N002"]}
    body = (await ai_client.post("/steam/news/ask", json=ask("진행 중인 이벤트 일정은?"))).json()
    assert body["refused"] is False and body["schedule"]["noCurrent"] is True
    assert body["answer"].startswith("진행 중이거나 예정된 일정을 공지에서 찾지 못했습니다.")
    body = (await ai_client.post("/steam/news/ask", json=ask("수확 축제 기간은?"))).json()
    assert body["schedule"]["noCurrent"] is False  # 특정 일정을 물으면 끝났어도 그대로 답이다

    fake_llm.reply = {"name": "Relic Hunt", "form": "FREE_UPDATE", "release_date": "2026-11-05",
                      "highlights": ["새 보스 Warden"], "sources": ["N002"]}
    body = (await ai_client.post("/steam/news/ask", json=ask("새로 추가된 콘텐츠는?"))).json()
    assert body["intent"] == "CONTENT" and body["schedule"] is None
    assert body["content"] == {"name": "Relic Hunt", "form": "FREE_UPDATE", "releaseDate": "2026-11-05",
                               "status": "ONGOING", "highlights": ["새 보스 Warden"]}
    assert "(최신 업데이트)" not in fake_llm.chats[-1][1]  # 최신 표시는 업데이트 요약에만


async def test_summary_english_lines_are_translated_once(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    english = "Arc Lance no longer clips through Glass Canyon walls."
    fake_llm.reply = [
        {"version": "1.1", "date": NEW_DAY, "new_features": ["로드아웃 공유"], "balance": [], "bug_fixes": [english],
         "sources": ["N002"]},
        {"translations": ["Arc Lance가 더 이상 Glass Canyon 벽을 통과하지 않음"]},
    ]
    body = (await ai_client.post("/steam/news/ask", json=ask("최신 업데이트에서 바뀐 점은?"))).json()
    assert body["summary"]["bugFixes"] == ["Arc Lance가 더 이상 Glass Canyon 벽을 통과하지 않음"]
    assert "Glass Canyon 벽을 통과하지 않음" in body["answer"]
    assert len(fake_llm.chats) == 2 and english in fake_llm.chats[1][1]  # 영어 줄만 번역 요청에
    # 답변 요청과 같은 num_ctx — 다르면 Ollama가 모델을 다시 올려 다음 질문까지 느려진다
    assert fake_llm.chats[1][2] == get_settings().qa_rag_num_ctx
    assert body["inputTokens"] == 100  # 응답의 입력 토큰은 답변 요청 기준


async def test_refusal_has_no_sources(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.reply = value_reply("근거 없음", ["N001", "N002"], "Phantom Scythe 쿨다운")
    body = (await ai_client.post("/steam/news/ask", json=ask("Phantom Scythe 쿨다운은?"))).json()
    assert body["refused"] is True and body["sources"] == [] and body["value"] is None
    # 판정용 "근거 없음" 대신 유형에 맞는 안내 문장(값 질문은 원문 이름으로 물어보라는 도움말 포함)
    assert body["answer"].startswith("최근 공지에서 이 수치를 찾지 못했습니다.") and "원문" in body["answer"]


async def test_broken_json_reply_is_reported_not_shown(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.reply = '{"target": "Arc Lance", "value": "4'  # 출력 한도에서 잘린 JSON
    body = (await ai_client.post("/steam/news/ask", json=ask())).json()
    assert body["refused"] is True and body["sources"] == [] and "다시 시도" in body["answer"]


async def test_doc_id_only_answer_becomes_title(ai_client, steam_handler, fake_llm):
    """자유 답을 "[N002]"처럼 문서 번호로만 하면 빈 답 대신 그 공지 제목을 보여 준다."""
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.reply = {"answer": "[N002]", "sources": ["N002"]}
    body = (await ai_client.post("/steam/news/ask", json=ask("Arc Lance 소식 알려줘"))).json()
    assert body["intent"] == "OTHER" and body["answer"] == "Patch 1.1" and body["refused"] is False


async def test_value_when_question_answers_version_from_title(ai_client, steam_handler, fake_llm):
    """"몇 버전에서 바뀌었나"는 마지막 기록의 버전. 모델이 버전을 비우면 공지 제목에서 채운다."""
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.reply = {"target": "Arc Lance 피해량", "sources": [],
                      "history": [{"doc": "N002", "version": "", "before": "46", "after": "48"}]}
    body = (await ai_client.post("/steam/news/ask", json=ask("Arc Lance는 몇 버전에서 바뀌었나요?"))).json()
    assert body["value"]["kind"] == "WHEN" and body["value"]["value"] == "1.1"
    assert body["answer"] == "1.1 (46 → 48)" and [s["gid"] for s in body["sources"]] == ["2002"]


async def test_schedule_drops_store_posts_unless_asked(ai_client, steam_handler, fake_llm):
    """상점 개편·드롭 글은 일정이 아니다("다음 업데이트 언제야?"에 "November Store Update"가 나열되던 문제).
    상점을 직접 물으면 남긴다. 남는 일정이 없으면 근거 없음."""
    notes = [item("5002", NEW, "November Store Update 2026", "[p]New skins in the store from Nov 3.[/p]"),
             item("5001", OLD, "Patch 44.1", "[p]Update 44.1 goes live on Nov 3.[/p]")]
    steam_handler["fn"] = news_handler(notes)
    store_item = {"name": "November Store Update 2026", "kind": "EVENT", "start": "2099-11-03", "end": ""}
    patch_item = {"name": "Update 44.1", "kind": "RELEASE", "start": "2099-11-03", "end": ""}
    fake_llm.reply = [{"items": [store_item, patch_item], "sources": ["N002", "N001"]},
                      {"items": [store_item], "sources": ["N002"]},
                      {"items": [store_item], "sources": ["N002"]}]

    body = (await ai_client.post("/steam/news/ask", json=ask("다음 업데이트 언제야?"))).json()
    assert [i["name"] for i in body["schedule"]["items"]] == ["Update 44.1"]
    assert [s["gid"] for s in body["sources"]] == ["5001"]

    only_store = (await ai_client.post("/steam/news/ask", json=ask("다음 업데이트 언제야?"))).json()
    assert only_store["refused"] is True and only_store["schedule"] is None

    asked = (await ai_client.post("/steam/news/ask", json=ask("상점 업데이트 언제야?"))).json()
    assert [i["name"] for i in asked["schedule"]["items"]] == ["November Store Update 2026"]


LINK = '[url="https://pubg.com/news/11306"]Read the full announcement here![/url]'


async def test_no_usable_news_skips_llm(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler([item("3001", NEW, "Read more", "[p][/p]")])  # 정리하면 본문이 빈 글
    body = (await ai_client.post("/steam/news/ask", json=ask())).json()
    assert body["refused"] is True and body["docCount"] == 0 and body["dateRange"] is None
    assert fake_llm.chats == []


async def test_link_only_notice_is_title_only_evidence(ai_client, steam_handler, fake_llm):
    """PRD v6.18: 본문이 외부 링크뿐인 공지는 빼지 않고 제목만 있는 글로 넣는다(점검 날짜가 제목에만 있는 경우).
    그 글을 근거로 쓰면 출처에 외부 원문 주소가 붙는다."""
    steam_handler["fn"] = news_handler([item("3002", NEW, "11/10(Tue) Maintenance Notice", LINK), two_notes()[1]])
    fake_llm.reply = {"items": [{"name": "정기 점검", "kind": "MAINTENANCE", "start": "2099-11-10", "end": ""}],
                      "sources": ["N002"]}

    body = (await ai_client.post("/steam/news/ask", json=ask("다음 점검 언제야?"))).json()

    assert body["intent"] == "SCHEDULE" and body["refused"] is False and body["docCount"] == 2
    user = fake_llm.chats[0][1]
    assert f"[N002] 11/10(Tue) Maintenance Notice ({NEW_DAY})" in user
    assert "전문은 외부 사이트 pubg.com에 있다" in user and "Read the full announcement" not in user
    assert body["sources"] == [{"gid": "3002", "title": "11/10(Tue) Maintenance Notice", "publishedAt": body["sources"][0]["publishedAt"],
                                "url": body["sources"][0]["url"], "externalUrl": "https://pubg.com/news/11306"}]


async def test_title_only_latest_patch_is_not_summarized(ai_client, steam_handler, fake_llm):
    """최신 패치 공지가 제목만 있으면 모델을 부르지 않고 원문으로 안내한다(제목으로 요약을 지어내지 않게)."""
    steam_handler["fn"] = news_handler([item("3003", NEW, "Patch Notes - Update 44.1", LINK), two_notes()[1]])

    body = (await ai_client.post("/steam/news/ask", json=ask("최신 업데이트에서 바뀐 점은?"))).json()

    assert fake_llm.chats == []
    assert body["intent"] == "UPDATE_SUMMARY" and body["refused"] is False and body["summary"] is None
    assert body["answer"] == "최신 업데이트 공지 'Patch Notes - Update 44.1'는 본문이 pubg.com에 있어 요약할 수 없어요. 원문에서 확인해 주세요."
    assert body["latestUpdate"]["gid"] == "3003" and body["sources"][0]["externalUrl"] == "https://pubg.com/news/11306"


async def test_title_only_news_post_is_not_latest_update(ai_client, steam_handler, fake_llm):
    """제목만 있는 공지는 엄격한 패치 제목일 때만 최신 업데이트 후보 — 개발자 편지는 본문 있는 패치 공지에 양보한다."""
    steam_handler["fn"] = news_handler([item("3004", NEW, "[Dev Letter] Anti-Cheat Update", LINK), two_notes()[1]])
    fake_llm.reply = {"version": "1.0", "date": OLD_DAY, "new_features": ["로드아웃"], "balance": [], "bug_fixes": [],
                      "sources": ["N001"]}

    body = (await ai_client.post("/steam/news/ask", json=ask("최신 업데이트에서 바뀐 점은?"))).json()

    assert body["latestUpdate"]["gid"] == "2001" and body["summary"]["version"] == "1.0"
    assert len(fake_llm.chats) == 1


async def test_large_corpus_uses_rag_top_k(ai_client, steam_handler, fake_llm):
    filler = "[p]" + "Bug fixes and stability improvements. " * 60 + "[/p]"  # 글마다 약 2,300자
    notes = [item(str(4000 + i), OLD + i * 3600, f"Patch {i}", filler) for i in range(20)]
    notes.append(item("4999", NEW, "Patch final", "[p]Arc Lance: damage changed from 46 to 48.[/p]"))
    steam_handler["fn"] = news_handler(sorted(notes, key=lambda n: -n["date"]))
    fake_llm.reply = value_reply("48", ["N021"])

    body = (await ai_client.post("/steam/news/ask", json=ask())).json()

    assert body["mode"] == "RAG" and body["docCount"] == 21
    assert [s["gid"] for s in body["sources"]] == ["4999"]
    _, user, num_ctx = fake_llm.chats[0]
    assert num_ctx == get_settings().qa_rag_num_ctx
    # 값 질문: Top-K만(최신 공지 고정·표시 없음). 조각을 10개로 늘린 v8 재실험은 latest가 떨어져 되돌림(PRD v6.11)
    assert user.count("\n\n---\n\n") == get_settings().qa_top_k - 1
    assert user.startswith("문서:\n[N021] Patch final")  # 질문과 가장 가까운 조각이 먼저
    assert fake_llm.embeds[-1] == ["Arc Lance 피해량은?"]


async def test_full_context_truncation_falls_back_to_rag(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    # 첫(Full Context) 호출은 입력이 한도에 닿았다고 응답 → 검색 모드로 다시 묻는다
    calls = iter([get_settings().qa_rag_num_ctx, 200])
    fake_llm.prompt_tokens = lambda num_ctx: next(calls)
    body = (await ai_client.post("/steam/news/ask", json=ask())).json()
    assert body["mode"] == "RAG" and body["inputTokens"] == 200
    assert len(fake_llm.chats) == 2


async def test_all_requests_share_one_num_ctx(ai_client, steam_handler, fake_llm):
    """Full Context·RAG·번역이 같은 num_ctx를 쓴다 — 다르면 Ollama가 바꿀 때마다 모델을 다시 올려 약 4초씩 늦었다
    (9단계 이후 측정: Blue Archive 2.9 → 6.4초, Terraria 3~4 → 11.4초)."""
    steam_handler["fn"] = news_handler(two_notes())
    await ai_client.post("/steam/news/ask", json=ask())
    assert fake_llm.chats[0][2] == get_settings().qa_rag_num_ctx  # 공지 2건이라 Full Context


# ---------------------------------------------------------------- 대상 범위·최신 업데이트·입력 검증


async def test_always_latest_posts_without_date_range(ai_client, steam_handler):
    calls: list[httpx.Request] = []
    steam_handler["fn"] = news_handler(two_notes(), calls)
    await ai_client.post("/steam/news/ask", json=ask())
    params = calls[0].url.params
    assert params["count"] == str(get_settings().qa_max_docs) and "enddate" not in params


async def test_latest_update_pinned_in_rag_even_if_question_matches_older_posts(ai_client, steam_handler, fake_llm):
    """의미 검색은 날짜를 보지 않으므로 최신 패치 공지의 조각을 항상 함께 넣는다."""
    old = "[p]" + "Arc Lance was rebalanced in this old update. " * 60 + "[/p]"
    latest = "[p]" + "New fishing system and boss rush mode. " * 60 + "[/p]"
    notes = [item(str(8000 + i), OLD + i * 3600, f"Patch 1.{i}", old) for i in range(12)]
    notes.append(item("8999", NEW, "Patch 2.0", latest))
    notes.append(item("9000", NEW + 3600, "State of the Game", "[p]" + "Community news. " * 50 + "[/p]"))
    steam_handler["fn"] = news_handler(sorted(notes, key=lambda n: -n["date"]))

    body = (await ai_client.post("/steam/news/ask", json=ask("Arc Lance 업데이트에서 바뀐 점은?"))).json()

    assert body["mode"] == "RAG"
    assert body["latestUpdate"]["gid"] == "8999"  # 제목에 버전이 없는 최근 소식 글은 최신 업데이트가 아니다
    user = fake_llm.chats[0][1]
    assert "(최신 업데이트) Patch 2.0" in user and "New fishing system" in user
    assert "(최신 업데이트) State of the Game" not in user

    # 같은 공지 목록이라도 값 질문에는 최신 공지를 고정하지 않는다(그 공지에 값이 없으면 "근거 없음"이 나오던 부작용)
    await ai_client.post("/steam/news/ask", json=ask("Arc Lance 피해량은 얼마야?"))
    user = fake_llm.chats[-1][1]
    assert "New fishing system" not in user and "(최신 업데이트)" not in user


async def test_schedule_rag_adds_recent_posts_except_store_and_merch(ai_client, steam_handler, fake_llm):
    """일정·콘텐츠 질문은 최근 공지(상점·굿즈 제외)마다 청크 1개를 더 넣는다 — 옛 이벤트만 걸리던 문제 대응."""
    old = "[p]" + "Arc Lance festival in an old season. " * 60 + "[/p]"
    notes = [item(str(8000 + i), OLD + i * 3600, f"Patch 1.{i}", old) for i in range(12)]
    notes.append(item("8999", NEW, "Hallowed Nights Returns", "[p]" + "Halloween event until Nov 9. " * 60 + "[/p]"))
    notes.append(item("9000", NEW + 3600, "Twitch Drops", "[p]" + "Watch streams for drops. " * 50 + "[/p]"))
    steam_handler["fn"] = news_handler(sorted(notes, key=lambda n: -n["date"]))
    fake_llm.reply = {"items": [], "sources": []}

    await ai_client.post("/steam/news/ask", json=ask("Arc Lance 이벤트는 언제야?"))
    user = fake_llm.chats[-1][1]
    assert "Halloween event" in user  # 질문과 닮지 않았어도 최근 공지라 들어간다
    assert "Watch streams" not in user  # 드롭 공지는 최근이어도 넣지 않는다

    await ai_client.post("/steam/news/ask", json=ask("Arc Lance 업데이트에서 바뀐 점은?"))
    assert "Halloween event" not in fake_llm.chats[-1][1]  # 요약은 최신 업데이트 고정만


async def test_rule_lines_in_body_do_not_look_like_doc_separators(ai_client, steam_handler, fake_llm):
    body = "[p]Part one[/p][p]---[/p][p]Part two[/p][p]=====[/p][p]End[/p]"
    steam_handler["fn"] = news_handler([item("9100", NEW, "Patch 3.0", body)])
    await ai_client.post("/steam/news/ask", json=ask())
    user = fake_llm.chats[0][1]
    assert "---" not in user and "=====" not in user and "Part one\n\nPart two\n\nEnd" in user


@pytest.mark.parametrize("payload", [
    ask("   "),
    ask("x" * 301),
    ask(dateRange={"from": "2026-10-01", "to": "2026-10-10"}),  # 없어진 항목은 조용히 무시하지 않는다
    {"appid": 0, "question": "q"},
    {"question": "q"},
])
async def test_invalid_input(ai_client, payload):
    res = await ai_client.post("/steam/news/ask", json=payload)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INVALID_INPUT"


async def test_unknown_game_is_not_found(ai_client, steam_handler):
    steam_handler["fn"] = news_handler([], status=403)
    res = await ai_client.post("/steam/news/ask", json=ask())
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------- 캐시·동시성·로그


async def test_corpus_and_index_cached_between_questions(ai_client, steam_handler, fake_llm):
    calls: list[httpx.Request] = []
    filler = "[p]" + "Stability improvements. " * 100 + "[/p]"
    notes = [item(str(6000 + i), OLD + i * 3600, f"Patch {i}", filler) for i in range(15)]
    steam_handler["fn"] = news_handler(sorted(notes, key=lambda n: -n["date"]), calls)

    for q in ("첫 질문", "둘째 질문"):
        assert (await ai_client.post("/steam/news/ask", json=ask(q))).json()["mode"] == "RAG"

    assert len(calls) == 1  # 같은 범위는 Steam을 다시 부르지 않는다
    chunk_batches = [b for b in fake_llm.embeds if len(b) > 1]
    assert len(chunk_batches) == 1  # 색인은 한 번만 만든다


async def test_questions_are_serialized_on_single_gpu(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.delay = 0.05
    results = await asyncio.gather(*(ai_client.post("/steam/news/ask", json=ask(f"질문 {i}")) for i in range(3)))
    assert all(r.status_code == 200 for r in results)
    assert fake_llm.max_active == 1 and len(fake_llm.chats) == 3


async def test_news_body_and_answer_not_logged(ai_client, steam_handler, fake_llm, caplog, monkeypatch):
    # DB 테스트의 Alembic 로깅 설정(disable_existing_loggers)이 앞서 돌면 이 로거들이 꺼져 있다
    for name in ("app.qa.service", "app.qa.llm", "app.news"):
        monkeypatch.setattr(logging.getLogger(name), "disabled", False)
    body = f"[p]{SECRET} " * 50 + "[/p]"
    steam_handler["fn"] = news_handler([item("7001", NEW, "Patch", body)])
    rag_ctx = get_settings().qa_rag_num_ctx
    fake_llm.prompt_tokens = lambda num_ctx: num_ctx if num_ctx != rag_ctx else 100  # 잘림 경고 경로까지 지나게
    fake_llm.reply = f"답: {SECRET}\n근거: N001, N404"
    with caplog.at_level(logging.DEBUG):
        res = await ai_client.post("/steam/news/ask", json=ask(f"{SECRET} 질문"))
    assert res.status_code == 200
    assert caplog.records and not any(SECRET in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- Ollama 호출부


def _ollama(handler) -> OllamaLlm:
    return OllamaLlm("http://ollama.test", 5.0, "bonsai-2:9b", "bge-m3", 1024, transport=httpx.MockTransport(handler))


async def test_ollama_chat_sends_experiment_options():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "답: 1"},
                                         "prompt_eval_count": 321, "done_reason": "stop"})

    llm = _ollama(handler)
    result = await llm.chat("sys", "user", 4096)
    await llm.aclose()
    assert result == ChatResult("답: 1", 321, "stop")
    body = seen[0]
    assert body["think"] is False and body["stream"] is False
    assert body["options"] == {"num_ctx": 4096, "num_predict": 1024, "temperature": 0, "seed": 1}


async def test_ollama_embed_batches_and_checks_count():
    sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        n = len(json.loads(request.content)["input"])
        sizes.append(n)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2]] * n})

    llm = _ollama(handler)
    assert len(await llm.embed([f"t{i}" for i in range(70)])) == 70
    assert sizes == [32, 32, 6]
    await llm.aclose()

    short = _ollama(lambda r: httpx.Response(200, json={"embeddings": [[0.1]]}))
    with pytest.raises(Exception) as exc:
        await short.embed(["a", "b"])
    assert getattr(exc.value, "code", None) == "AI_UNAVAILABLE"
    await short.aclose()


def _raise(exc: Exception):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc
    return handler


@pytest.mark.parametrize("handler", [
    _raise(httpx.ConnectError("refused")),
    _raise(httpx.ReadTimeout("slow")),
    lambda r: httpx.Response(404, json={"error": "model 'bonsai-2:9b' not found"}),
    lambda r: httpx.Response(200, text="not json"),
    lambda r: httpx.Response(200, json={"unexpected": True}),
])
async def test_ollama_failures_become_ai_unavailable(handler):
    from app.errors import AppError

    llm = _ollama(handler)
    with pytest.raises(AppError) as exc:
        await llm.chat("sys", "user", 4096)
    await llm.aclose()
    assert exc.value.code == "AI_UNAVAILABLE" and exc.value.status_code == 503


# ---------------------------------------------------------------- 질문 유형·답변 틀(지시문 v5)


@pytest.mark.parametrize(("question", "intent"), [
    ("최신 업데이트에서 바뀐 점은?", "UPDATE_SUMMARY"),
    ("최근 패치 내용 알려줘", "UPDATE_SUMMARY"),
    ("1.4.5.7에서 추가된 기능은?", "UPDATE_SUMMARY"),
    ("Unholy Trident 피해량은 지금 얼마야?", "VALUE"),
    ("Arc Lance 피해량은 언제 바뀌었나요?", "VALUE"),  # "언제"가 있어도 값 질문이 먼저
    ("Tide Caller는 몇 버전에서 추가되었나요?", "VALUE"),
    ("수확 축제 이벤트는 언제 끝나나요?", "SCHEDULE"),
    ("다음 점검은 언제야?", "SCHEDULE"),
    ("다음 DLC는 언제 나와?", "SCHEDULE"),  # 날짜를 물으면 콘텐츠보다 일정이 먼저
    ("지금 진행 중인 이벤트 있어?", "SCHEDULE"),  # "언제" 없이 이벤트·진행 중만 물어도 일정(2026-11-07)
    ("예정된 이벤트 알려줘", "SCHEDULE"),
    ("이벤트 보상은 얼마야?", "VALUE"),  # 수치를 물으면 여전히 값이 먼저
    ("새로 추가된 콘텐츠는?", "CONTENT"),
    ("이번 DLC에는 뭐가 있어?", "CONTENT"),
    ("새 맵 소식 있어?", "CONTENT"),
    ("2.4.1 패치노트의 알려진 문제는?", "OTHER"),  # "패치노트"는 출처 지칭일 뿐 요약 요청이 아니다
    ("이 게임 재미있어?", "OTHER"),
])
def test_classify(question, intent):
    from app.qa.templates import classify

    assert classify(question) == intent


def test_summary_parse_caps_items_and_cleans_ids():
    from app.qa.templates import QaIntent as I
    from app.qa.templates import parse, render

    raw = json.dumps({"version": "1.4.5.7", "date": "2026-08-19",
                      "new_features": ["로드아웃 공유 (N047)", "부활 대기 건너뛰기", "세 번째는 버린다"],
                      "balance": [], "bug_fixes": ["  "], "sources": ["[N047] Terraria 1.4.5.7", "N047"]},
                     ensure_ascii=False)
    filled = parse(I.UPDATE_SUMMARY, raw)
    assert filled.new_features == ["로드아웃 공유", "부활 대기 건너뛰기"] and filled.bug_fixes == []
    assert filled.sources == ["N047"]
    assert render(filled) == ("1.4.5.7 (2026-08-19)\n- 새 기능: 로드아웃 공유; 부활 대기 건너뛰기", False)


def test_empty_summary_is_refusal():
    from app.qa.templates import UpdateSummary, render

    assert render(UpdateSummary(version="1.0")) == ("근거 없음", True)


TODAY = date(2026, 11, 5)


@pytest.mark.parametrize(("start", "end", "single_day", "status"), [
    ("2026-11-10", "2026-11-20", False, "UPCOMING"),
    ("2026-11-01", "2026-11-20", False, "ONGOING"),
    ("2026-11-01", "2026-11-05", False, "ONGOING"),  # 끝나는 날까지 진행 중
    ("2026-08-01", "2026-08-31T19:00:00", False, "ENDED"),  # 시각은 버리고 날짜만 비교
    ("2026-11-05", "", True, "ONGOING"),  # 하루짜리(출시일)는 그날
    ("2026-08-19", "", True, "ENDED"),
    ("2026-10-13", "", False, "UNKNOWN"),  # 시작만 아는 이벤트는 끝났는지 모른다
    ("2026-09-06", "", False, "UNKNOWN"),  # 시작 후 60일째까지는 모른다
    ("2026-09-05", "", False, "ENDED"),  # 60일이 넘으면 끝난 것으로 본다(작년 Winter's Feast 등)
    ("2025-12-18", "", False, "ENDED"),
    ("2026-11-13", "", False, "UPCOMING"),
    ("", "2026-11-30", False, "ONGOING"),  # 종료만 있으면 그날까지 진행 중
    ("", "2026. 10. 31.", False, "ENDED"),
    ("곧", "", True, "UNKNOWN"),
    ("2026-02-30", "", True, "UNKNOWN"),  # 없는 날짜
])
def test_status_by_kst_date(start, end, single_day, status):
    from app.qa.templates import status_of

    assert status_of(start, end, TODAY, single_day) == status


def test_schedule_parse_drops_undated_sorts_by_status_and_caps():
    from app.qa.templates import QaIntent as I
    from app.qa.templates import parse, render

    raw = json.dumps({"items": [
        {"name": "Speedrun Contest", "kind": "EVENT", "start": "", "end": "2026-08-31T19:00:00"},
        {"name": "날짜 없는 행사", "kind": "EVENT", "start": "", "end": ""},
        {"name": "근거 없음", "kind": "EVENT", "start": "2026-11-01", "end": ""},
        {"name": "Silk & Silver 출시", "kind": "RELEASE", "start": "2026-11-17", "end": ""},
        {"name": "Hallowed Nights", "kind": "SEASON?", "start": "2026-10-26", "end": "2026-11-09"},
    ], "sources": ["N003"]}, ensure_ascii=False)
    filled = parse(I.SCHEDULE, raw, today=TODAY)
    assert [(i.name, i.status) for i in filled.items] == [
        ("Hallowed Nights", "ONGOING"), ("Silk & Silver 출시", "UPCOMING"), ("Speedrun Contest", "ENDED")]
    assert filled.items[0].kind == "EVENT"  # 모르는 종류 하나 때문에 답 전체를 버리지 않는다
    expected = ("Hallowed Nights: 2026-10-26 ~ 2026-11-09 (진행 중)\n"
                "Silk & Silver 출시: 2026-11-17 (예정)\n"
                "Speedrun Contest: ~ 2026-08-31T19:00:00 (종료)")
    assert render(filled) == (expected, False)
    assert render(parse(I.SCHEDULE, '{"items": [], "sources": []}', today=TODAY)) == ("근거 없음", True)


def test_content_parse_status_and_refusal():
    from app.qa.templates import QaIntent as I
    from app.qa.templates import parse, render

    raw = json.dumps({"name": "Silk & Silver", "form": "EXPANSION", "release_date": "2026-11-17",
                      "highlights": ["무역 체계", "구엘프·기벨린", "새 음악", "네 번째는 버린다"], "sources": ["N010"]},
                     ensure_ascii=False)
    filled = parse(I.CONTENT, raw, today=TODAY)
    assert filled.status == "UPCOMING" and len(filled.highlights) == 3
    assert render(filled) == ("Silk & Silver (2026-11-17)\n- 무역 체계\n- 구엘프·기벨린\n- 새 음악", False)
    empty = parse(I.CONTENT, '{"name": "근거 없음", "form": "X", "release_date": "", "highlights": [], "sources": []}')
    assert empty.form == "OTHER" and render(empty) == ("근거 없음", True)


@pytest.mark.parametrize(("title", "scale", "test"), [
    ("Live Update 2.3.0", "MAJOR", False),
    ("Euro Truck Simulator 2: 1.62 Update Release", "MAJOR", False),
    ("Terraria 1.4.5.7 - Out Now for PC!", "PATCH", False),
    ("Update 1.20.1.2", "PATCH", False),
    ("Counter-Strike 2 Update", "PATCH", False),
    ("7.41f Gameplay Patch", "PATCH", False),  # 글자가 붙은 버전은 보지 않는다
    ("Hotfix 2.4.1", "HOTFIX", False),
    ("Hotifix 760944", "HOTFIX", False),  # 실제 공지의 오타
    ("10.2.2 | Bugfix Patch", "HOTFIX", False),
    ("V3.4.0 EXP", "MAJOR", True),
    ("10.3.0 | Terrifier PTB Patch Notes", "MAJOR", True),
    ("Open Beta for Performance", "PATCH", True),
])
def test_update_scale_and_build_from_title(title, scale, test):
    from app.qa.prompt import is_test_build, update_scale

    assert update_scale(title) == scale and is_test_build(title) is test


@pytest.mark.parametrize(("title", "version"), [
    ("Update 1.20.1.2", "1.20.1.2"),
    ("V3.4.0 Stable -b9 hotfix", "3.4.0"),
    ("Hotfix 761239", ""),  # 빌드 번호는 버전이 아니다
    ("7.41f Gameplay Patch", ""),
])
def test_title_version(title, version):
    from app.qa.prompt import title_version

    assert title_version(title) == version


async def test_summary_version_falls_back_to_title(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    fake_llm.reply = {"version": "", "date": NEW_DAY, "new_features": ["로드아웃 공유"], "balance": [], "bug_fixes": [],
                      "sources": ["N002"]}
    body = (await ai_client.post("/steam/news/ask", json=ask("최신 업데이트에서 바뀐 점은?"))).json()
    assert body["summary"]["version"] == "1.1" and body["answer"].startswith("1.1 (")


def test_maintenance_with_start_only_is_one_day():
    from app.qa.templates import QaIntent as I
    from app.qa.templates import parse

    raw = json.dumps({"items": [{"name": "정기 점검", "kind": "MAINTENANCE", "start": "2026-10-27", "end": ""},
                                {"name": "할로윈", "kind": "EVENT", "start": "2026-10-27", "end": ""}],
                      "sources": []}, ensure_ascii=False)
    filled = parse(I.SCHEDULE, raw, today=TODAY)
    assert [i.status for i in filled.items] == ["UNKNOWN", "ENDED"]  # 이벤트는 모름(앞으로), 점검은 그날로 끝


def test_latest_update_skips_store_merch_and_prefers_stable():
    from app.qa.prompt import latest_update_id

    # 오래된 글부터. "Store Update"는 상점 개편, 드롭·굿즈는 업데이트가 아니다
    assert latest_update_id([("N1", "Hotfix 2.3.1"), ("N2", "Store Update 2.4.0"), ("N3", "Twitch Drops!")]) == "N1"
    assert latest_update_id([("N1", "V3.3.0 Stable"), ("N2", "V3.4.0 EXP")]) == "N1"
    assert latest_update_id([("N1", "Community Wrap-Up"), ("N2", "V3.4.0 EXP")]) == "N2"  # 정식이 없으면 테스트
    assert latest_update_id([("N1", "Dev Diary"), ("N2", "Mini Replicas Arrive")]) == "N1"
    assert latest_update_id([("N1", "Plushie!")]) == "N1"
    assert latest_update_id([]) is None


def test_parse_rejects_broken_json_and_strips_thinking():
    from app.qa.templates import QaIntent as I
    from app.qa.templates import parse

    assert parse(I.VALUE, '{"value": "4') is None
    filled = parse(I.OTHER, '<think>...</think>{"answer": "Relic Hunt", "sources": []}')
    assert filled.answer == "Relic Hunt"


def test_schema_matches_parser_fields():
    from app.qa.templates import _MODELS, SERVER_FIELDS, QaIntent, json_schema

    for intent in QaIntent:
        # 상태·계산 결과는 서버가 채우는 칸이라 모델에 요구하지 않는다
        assert set(json_schema(intent)["required"]) == set(_MODELS[intent].model_fields) - SERVER_FIELDS


# ---------------------------------------------------------------- 미리 준비(PRD v6.15)


async def _wait_warm(app) -> None:
    for _ in range(100):
        if not app.state.qa._warming:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("warmup did not finish")


async def test_warmup_disabled_by_default(client, steam_handler):
    res = await client.post(f"/steam/news/{APPID}/ask/warmup")
    assert res.status_code == 403 and res.json()["error"]["code"] == "FEATURE_DISABLED"


async def test_warmup_builds_index_once_and_question_reuses_it(ai_client, steam_handler, fake_llm):
    filler = "[p]" + "Bug fixes and stability improvements. " * 60 + "[/p]"  # 공지가 많아 RAG가 필요한 게임
    notes = [item(str(4000 + i), OLD + i * 3600, f"Patch {i}", filler) for i in range(20)]
    notes.append(item("4999", NEW, "Patch final", "[p]Arc Lance: damage changed from 46 to 48.[/p]"))
    calls: list = []
    steam_handler["fn"] = news_handler(sorted(notes, key=lambda n: -n["date"]), calls)

    res = await ai_client.post(f"/steam/news/{APPID}/ask/warmup")
    assert res.status_code == 202 and res.json() == {"status": "STARTED"}
    await _wait_warm(ai_client.app)
    assert len(fake_llm.embeds) == 1 and fake_llm.chats == []  # 색인만 만들고 답은 만들지 않는다
    assert (await ai_client.post(f"/steam/news/{APPID}/ask/warmup")).json() == {"status": "READY"}

    fake_llm.reply = value_reply("48", ["N021"])
    body = (await ai_client.post("/steam/news/ask", json=ask())).json()
    assert body["mode"] == "RAG" and body["value"]["value"] == "48"
    assert len(fake_llm.embeds) == 2 and fake_llm.embeds[-1] == ["Arc Lance 피해량은?"]  # 질문 임베딩만 더해짐
    assert len(calls) == 1  # 공지도 다시 받지 않는다


async def test_warmup_small_corpus_needs_no_index(ai_client, steam_handler, fake_llm):
    steam_handler["fn"] = news_handler(two_notes())
    await ai_client.post(f"/steam/news/{APPID}/ask/warmup")
    await _wait_warm(ai_client.app)
    assert fake_llm.embeds == []  # 공지 전체를 넣는 게임은 색인이 필요 없다
    assert (await ai_client.post(f"/steam/news/{APPID}/ask/warmup")).json() == {"status": "READY"}


async def test_warmup_and_question_share_one_corpus_fetch(ai_client, steam_handler, fake_llm):
    calls: list = []
    steam_handler["fn"] = news_handler(two_notes(), calls)
    await asyncio.gather(ai_client.post(f"/steam/news/{APPID}/ask/warmup"), ai_client.post("/steam/news/ask", json=ask()))
    await _wait_warm(ai_client.app)
    assert len(calls) == 1  # 동시에 와도 공지는 한 번만 받는다


def test_recent_ids_skip_store_and_hotfix_posts():
    """일정·콘텐츠 질문의 최근 공지: 상점·굿즈와 핫픽스는 뺀다 — DST처럼 최근 5건이 모두 핫픽스면
    바로 앞의 이벤트 공지("Hallowed Nights Returns!")가 밀려났다."""
    from app.qa.prompt import recent_ids

    docs = [("N001", "Klei Fest Coming June 11th!"), ("N002", "Hallowed Nights Returns!"),
            ("N003", "Hotfix 760178"), ("N004", "Hotifix 760944"), ("N005", "November Store Update"),
            ("N006", "Hotfix 762113"), ("N007", "Patch 1.2 Notes")]
    assert recent_ids(docs, 3) == ["N007", "N002", "N001"]


def test_latest_update_skips_report_posts():
    """같은 날 "Patch Notes - Update 44.1" 뒤에 올라온 "Map Service Report - Update 44.1"(맵 순환 안내)은 최신 업데이트가 아니다."""
    from app.qa.prompt import latest_update_id

    docs = [("N001", "Patch Notes - Update 43.2"), ("N002", "Patch Notes - Update 44.1"),
            ("N003", "Map Service Report - Update 44.1"), ("N004", "November Store Update 2026")]
    assert latest_update_id(docs) == "N002"
    assert latest_update_id([("N001", "Map Service Report - Update 44.1")]) == "N001"  # 다른 글이 없으면 그 글이라도



async def test_started_post_titles_become_schedule_items(ai_client, steam_handler, fake_llm, monkeypatch):
    """본문에 날짜가 없는 "지금 시작" 꼴 공지(DST "Hallowed Nights Returns!")는 서버가 게시일(한국 날짜) 시작 일정으로 더한다.
    모델이 이미 쓴 공지·앞으로의 일·점검 질문·묻지 않은 종류에는 더하지 않는다."""
    from app.qa import service

    monkeypatch.setattr(service, "today_kst", lambda: date(2026, 11, 7))
    returns = item("6003", 1793026800, "Hallowed Nights Returns!", "[p]Trick or treat![/p]")  # 2026-10-26 15:00 UTC = 10/27 KST
    out_now = item("6002", 1792940400, "Cursed Confrontation Part 2 - Out Now!", "[p]New boss.[/p]")  # 10/26 KST
    coming = item("6001", 1792854000, "Klei Fest Coming June 11th!", "[p]Soon.[/p]")
    steam_handler["fn"] = news_handler([returns, out_now, coming])
    fake_llm.reply = {"items": [], "sources": []}

    body = (await ai_client.post("/steam/news/ask", json=ask("지금 진행 중인 이벤트 있어?"))).json()
    assert body["refused"] is False
    assert body["schedule"]["items"] == [{"name": "Hallowed Nights Returns!", "kind": "EVENT", "start": "2026-10-27",
                                          "end": "", "status": "UNKNOWN", "fromPostDate": True}]
    assert [s["gid"] for s in body["sources"]] == ["6003"]

    both = (await ai_client.post("/steam/news/ask", json=ask("최근 일정 알려줘"))).json()  # 종류를 안 물으면 출시도
    assert [(i["name"], i["status"]) for i in both["schedule"]["items"]] == [
        ("Hallowed Nights Returns!", "UNKNOWN"), ("Cursed Confrontation Part 2 - Out Now!", "ENDED")]

    maintenance = (await ai_client.post("/steam/news/ask", json=ask("다음 점검 언제야?"))).json()
    assert maintenance["refused"] is True  # 점검만 물으면 이벤트를 더하지 않는다

    specific = (await ai_client.post("/steam/news/ask", json=ask("Winter's Feast 기간은?"))).json()
    assert specific["refused"] is True  # 특정 일정을 물으면(지금·다음·최근 없음) 상관없는 공지를 더하지 않는다

    fake_llm.reply = {"items": [{"name": "Hallowed Nights", "kind": "EVENT", "start": "2026-10-27", "end": "2026-11-10"}],
                      "sources": ["N003"]}
    cited = (await ai_client.post("/steam/news/ask", json=ask("지금 진행 중인 이벤트 있어?"))).json()
    assert [i["fromPostDate"] for i in cited["schedule"]["items"]] == [False]  # 모델이 쓴 공지는 다시 더하지 않는다


def test_started_kind_title_rules():
    from app.qa.prompt import started_kind

    assert started_kind("Don't Starve Together - Hallowed Nights Returns!") == "EVENT"
    assert started_kind("Winter's Feast Has Arrived! + More") == "EVENT"
    assert started_kind("Season 27 is now live") == "EVENT"
    assert started_kind("Cursed Confrontation Part 2 - Out Now!") == "RELEASE"
    assert started_kind("Update 44.1 is now live") == "RELEASE"  # 업데이트·버전 제목은 이벤트가 아니다
    assert started_kind("V3.4.0 Stable is live") == "RELEASE"
    assert started_kind("Cursed Confrontation Part 2 Releases October 22nd!") is None  # 앞으로의 출시
    assert started_kind("Klei Fest Coming June 11th!") is None
    assert started_kind("Ranked Returns Next Week") is None
    assert started_kind("11/10(Tue) Maintenance Notice") is None
    assert started_kind("Store Sale Is Live") is None  # 상점 글
