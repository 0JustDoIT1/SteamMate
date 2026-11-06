"""내 게임 소식(PRD v6.15): 최근 플레이 순 대상, 날짜순 병합, 패치 규모, 일부 실패 허용, 로그인 필요."""

import httpx

from tests.conftest import TEST_STEAM_ID
from tests.test_me_library import OWNED
from tests.test_news import NEWS, item

DAY = 86_400
NOW = 1_793_300_000


def owned(*games: tuple[int, str, int, int]) -> dict:
    """(appid, 이름, 최근 2주 분, 마지막 실행 시각)"""
    return {"response": {"game_count": len(games), "games": [
        {"appid": a, "name": n, "playtime_forever": 600, "playtime_2weeks": w, "rtime_last_played": t}
        for a, n, w, t in games]}}


def handler(owned_body: dict, news_by_appid: dict[int, list[dict] | int]):
    calls: list[str] = []

    def fn(request: httpx.Request) -> httpx.Response:
        if request.url.path == OWNED:
            return httpx.Response(200, json=owned_body)
        assert request.url.path == NEWS
        appid = int(request.url.params["appid"])
        calls.append(str(appid))
        news = news_by_appid[appid]
        if isinstance(news, int):  # 이 게임은 Steam 오류
            return httpx.Response(news, json={})
        count = int(request.url.params["count"])
        return httpx.Response(200, json={"appnews": {"appid": appid, "newsitems": news[:count], "count": len(news)}})

    fn.calls = calls
    return fn


async def test_requires_login(client):
    assert (await client.get("/me/news-feed")).status_code == 401


async def test_recent_games_merged_by_date_with_patch_scale(client, login, steam_handler):
    fn = handler(
        owned(
            (10, "Recent A", 300, NOW - DAY),  # 최근 2주에 가장 많이 함
            (20, "Recent B", 0, NOW - 2 * DAY),  # 최근 2주엔 안 했지만 최근에 실행
            (30, "Never", 0, 0),  # 한 번도 실행 안 함 → 대상 아님
        ),
        {
            10: [item("101", NOW - 3 * DAY, "Hotfix 2.4.1"), item("102", NOW - 10 * DAY, "Dev Diary #4")],
            20: [item("201", NOW - DAY, "Update 1.20.0"), item("202", NOW - 20 * DAY, "Twitch Drops 2.0")],
        },
    )
    steam_handler["fn"] = fn
    login()

    body = (await client.get("/me/news-feed")).json()

    assert body["gameCount"] == 2 and body["failedCount"] == 0
    assert sorted(fn.calls) == ["10", "20"]  # 실행 안 한 게임은 부르지 않는다
    assert [(i["gid"], i["gameName"], i["scale"]) for i in body["items"]] == [
        ("201", "Recent B", "MAJOR"),  # 날짜순(최신 먼저)
        ("101", "Recent A", "HOTFIX"),
        ("102", "Recent A", None),  # 패치 꼴이 아닌 공지
        ("202", "Recent B", None),  # 드롭 공지는 버전 번호가 있어도 패치가 아니다
    ]


async def test_one_game_failing_does_not_hide_others(client, login, steam_handler):
    steam_handler["fn"] = handler(
        owned((10, "Ok", 60, NOW), (20, "Broken", 30, NOW)),
        {10: [item("101", NOW, "Patch 1.1")], 20: 500},
    )
    login(TEST_STEAM_ID)
    body = (await client.get("/me/news-feed")).json()
    assert [i["gid"] for i in body["items"]] == ["101"] and body["failedCount"] == 1


def test_is_patch_title_skips_news_posts_without_version():
    from app.qa.prompt import is_patch_title

    assert is_patch_title("Counter-Strike 2 Update")
    assert is_patch_title("Hotfix 761239")
    assert is_patch_title("Developer Update | 10.2.0 PTB to Live Changes")  # 버전 번호가 있으면 패치
    assert not is_patch_title("[Dev Letter] Anti-Cheat Update - Combating Cheat Distribution")
    assert not is_patch_title("Bungie Community Update – October 2026")
    assert not is_patch_title("November Store Update 2026")  # 상점 글
    assert not is_patch_title("Terraria State of the Game - October 2026")
