from datetime import UTC, datetime

import httpx
import pytest

from app.metadata.service import MetadataSnapshot
from app.models import FetchStatus

NEWS = "/ISteamNews/GetNewsForApp/v2/"
LONG_BODY = "SECRET-TAIL " * 500  # 발췌 뒤쪽 본문이 응답에 섞이지 않는지 확인용


def item(gid: str, date: int, title: str = "Patch", contents: str | None = None) -> dict:
    return {
        "gid": gid,
        "title": title,
        "url": "https://steamstore-a.akamaihd.net/news/externalpost/steam_community_announcements/1",
        "is_external_url": True,
        "author": "Dev",
        "contents": contents if contents is not None else f"[p]Notes for {gid}[/p]",
        "feedlabel": "Community Announcements",
        "date": date,
        "feedname": "steam_community_announcements",
        "feed_type": 1,
        "appid": 105600,
    }


def news_handler(items: list[dict], calls: list[httpx.Request] | None = None, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == NEWS
        if calls is not None:
            calls.append(request)
        if status != 200:
            return httpx.Response(status, json={})
        count = int(request.url.params["count"])
        end = request.url.params.get("enddate")
        page = [i for i in items if end is None or i["date"] <= int(end)][:count]
        return httpx.Response(200, json={"appnews": {"appid": 105600, "newsitems": page, "count": len(items)}})

    return handler


async def test_lists_official_news_with_excerpt_and_store_link(client, steam_handler, fake_metadata):
    fake_metadata.snapshots = {105600: MetadataSnapshot(105600, FetchStatus.SUCCESS, "game", (), None, name="Terraria", header_image="https://img/h.jpg")}
    calls: list[httpx.Request] = []
    body = "[img]{STEAM_CLAN_IMAGE}/1/a.png[/img][h2]Update 1.4.5[/h2][p]Greetings [b]Terrarians[/b]![/p]" + LONG_BODY
    steam_handler["fn"] = news_handler([item("1001", 1793300000, contents=body), item("1000", 1793200000)], calls)

    res = await client.get("/steam/news/105600", params={"count": 1})

    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Terraria" and data["headerImage"] == "https://img/h.jpg"
    first = data["items"][0]
    assert first["url"] == "https://store.steampowered.com/news/app/105600/view/1001"
    assert first["excerpt"].startswith("Update 1.4.5 Greetings Terrarians!") and first["excerpt"].endswith("…")
    assert len(first["excerpt"]) <= 201
    assert res.text.count("SECRET-TAIL") < 20  # 본문 전문(500번 반복)을 내보내지 않고 앞부분 발췌만
    assert first["publishedAt"] == datetime.fromtimestamp(1793300000, UTC).isoformat().replace("+00:00", "Z")
    # 하나 더 있으므로 다음 페이지 기준 시각을 준다(같은 시각 겹침 방지로 1초 앞)
    assert data["nextBefore"] == 1793300000 - 1
    assert first["externalUrl"] is None
    params = calls[0].url.params
    assert params["feeds"] == "steam_community_announcements" and params["count"] == "2"
    assert "maxlength" not in params and "key" not in params


async def test_next_page_uses_enddate_and_ends(client, steam_handler):
    calls: list[httpx.Request] = []
    steam_handler["fn"] = news_handler([item("3", 300), item("2", 200), item("1", 100)], calls)

    data = (await client.get("/steam/news/105600", params={"count": 2, "before": 199})).json()

    assert calls[0].url.params["enddate"] == "199"
    assert [i["gid"] for i in data["items"]] == ["1"] and data["nextBefore"] is None


async def test_cached_in_memory(client, steam_handler):
    calls: list[httpx.Request] = []
    steam_handler["fn"] = news_handler([item("1", 100)], calls)
    await client.get("/steam/news/105600")
    await client.get("/steam/news/105600")
    assert len(calls) == 1


async def test_skips_unexpected_gid(client, steam_handler):
    steam_handler["fn"] = news_handler([item("abc/../x", 200), item("7", 100)])
    data = (await client.get("/steam/news/105600")).json()
    assert [i["gid"] for i in data["items"]] == ["7"]


@pytest.mark.parametrize(
    ("status", "http_status", "code"),
    [(403, 404, "NOT_FOUND"), (429, 503, "STEAM_RATE_LIMITED"), (500, 502, "STEAM_UNAVAILABLE")],
)
async def test_steam_errors(client, steam_handler, status, http_status, code):
    steam_handler["fn"] = news_handler([], status=status)
    res = await client.get("/steam/news/999999999")
    assert res.status_code == http_status and res.json()["error"]["code"] == code


async def test_schema_mismatch_and_timeout(client, steam_handler):
    steam_handler["fn"] = lambda r: httpx.Response(200, json={"unexpected": True})
    assert (await client.get("/steam/news/1")).json()["error"]["code"] == "STEAM_UNAVAILABLE"

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    steam_handler["fn"] = slow
    assert (await client.get("/steam/news/2")).json()["error"]["code"] == "STEAM_TIMEOUT"


@pytest.mark.parametrize(
    ("path", "params"),
    [("/steam/news/0", {}), ("/steam/news/abc", {}), ("/steam/news/1", {"count": 21}), ("/steam/news/1", {"before": 0})],
)
async def test_invalid_input(client, path, params):
    res = await client.get(path, params=params)
    assert res.status_code == 422 and res.json()["error"]["code"] == "INVALID_INPUT"


async def test_no_login_required(client, steam_handler):
    steam_handler["fn"] = news_handler([item("1", 100)])
    assert (await client.get("/steam/news/105600")).status_code == 200


async def test_link_only_post_has_external_url_and_no_excerpt(client, steam_handler):
    stub = '[img]{STEAM_CLAN_IMAGE}/1/a.jpg[/img][h2][url="https://pubg.com/news/1"]Read the full announcement here![/url][/h2]'
    steam_handler["fn"] = news_handler([item("5", 100, contents=stub)])
    first = (await client.get("/steam/news/578080")).json()["items"][0]
    assert first["externalUrl"] == "https://pubg.com/news/1" and first["excerpt"] == ""
