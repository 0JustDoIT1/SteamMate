"""거의 다 깬 게임(PRD v6.16): 대상 고르기, 60~99% 순위, 남은 업적 이름, 비공개, 캐시, 한 게임 실패."""

import httpx

from tests.test_me_library import OWNED

ACH = "/ISteamUserStats/GetPlayerAchievements/v1/"
SCHEMA = "/ISteamUserStats/GetSchemaForGame/v2/"


def owned(*games: tuple[int, str, int]) -> dict:
    """(appid, 이름, 총 플레이 분)"""
    return {"response": {"game_count": len(games), "games": [
        {"appid": a, "name": n, "playtime_forever": m, "rtime_last_played": 1} for a, n, m in games]}}


def ach(done: int, total: int) -> dict:
    return {"playerstats": {"success": True, "achievements": [
        {"apiname": f"A{i}", "achieved": 1 if i < done else 0} for i in range(total)]}}


def steam(owned_body: dict, by_appid: dict[int, dict | httpx.Response], names: dict[int, dict[str, str]] | None = None):
    calls: list[tuple[str, int]] = []

    def fn(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == OWNED:
            return httpx.Response(200, json=owned_body)
        appid = int(request.url.params["appid"])
        calls.append((path, appid))
        if path == SCHEMA:
            achievements = [{"name": k, "displayName": v} for k, v in (names or {}).get(appid, {}).items()]
            return httpx.Response(200, json={"game": {"availableGameStats": {"achievements": achievements}}})
        assert path == ACH
        result = by_appid[appid]
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    fn.calls = calls
    return fn


NO_STATS = httpx.Response(400, json={"playerstats": {"error": "Requested app has no stats", "success": False}})
PRIVATE = httpx.Response(403, json={"playerstats": {"error": "Profile is not public", "success": False}})


async def test_requires_login(client):
    assert (await client.get("/me/achievements")).status_code == 401


async def test_nearly_done_ranked_with_remaining_names(client, login, steam_handler):
    fn = steam(
        owned(
            (1, "PUBG", 100_000), (2, "FM24", 50_000), (3, "RimWorld", 40_000), (4, "Warhammer", 7_000),
            (5, "Siege", 26_000), (6, "BG3", 14_000), (7, "Short", 30), (8, "Never", 0),
        ),
        {1: ach(35, 37), 2: ach(74, 100), 3: NO_STATS, 4: ach(138, 138), 5: ach(0, 48), 6: ach(32, 54), 7: ach(9, 10)},
        names={1: {"A35": "치킨 10번", "A36": "탑 10 100번"}},
    )
    steam_handler["fn"] = fn
    login()

    body = (await client.get("/me/achievements")).json()

    assert body["status"] == "OK"
    # 30분만 한 게임도 업적을 90% 모았으면 들어간다(보유 게임 전부 확인)
    assert [(g["name"], g["achieved"], g["total"]) for g in body["nearlyDone"]] == [
        ("PUBG", 35, 37), ("Short", 9, 10), ("FM24", 74, 100)]
    assert body["nearlyDone"][0]["remaining"] == ["치킨 10번", "탑 10 100번"]  # 아직 안 한 업적 이름(한국어)
    assert body["nearlyDone"][2]["remaining"] == []  # 이름을 못 받아도 진행률은 보인다
    assert body["completedCount"] == 1  # Warhammer 100%
    assert body["checkedCount"] == 6  # 업적 없는 RimWorld 제외, 59% BG3·0% Siege는 확인만
    assert (ACH, 8) not in fn.calls  # 한 번도 실행 안 한 게임은 부르지 않는다
    assert {a for p, a in fn.calls if p == SCHEMA} == {1, 2, 7}  # 이름은 보여 줄 게임만


async def test_private_achievements(client, login, steam_handler):
    steam_handler["fn"] = steam(owned((1, "PUBG", 1000), (2, "FM24", 900)), {1: PRIVATE, 2: PRIVATE})
    login()
    body = (await client.get("/me/achievements")).json()
    assert body["status"] == "PRIVATE" and body["nearlyDone"] == []


async def test_cached_and_failed_game_retried_later(client, login, steam_handler):
    fn = steam(owned((1, "PUBG", 1000), (2, "Broken", 900)), {1: ach(9, 10), 2: httpx.Response(500, json={})})
    steam_handler["fn"] = fn
    login()
    first = (await client.get("/me/achievements")).json()
    assert [g["name"] for g in first["nearlyDone"]] == ["PUBG"] and first["checkedCount"] == 1

    await client.get("/me/achievements")
    ach_calls = [a for p, a in fn.calls if p == ACH]
    assert ach_calls.count(1) == 1  # 성공한 게임은 캐시(6시간)
    assert ach_calls.count(2) == 2  # 실패한 게임은 캐시하지 않고 다시 시도
