from datetime import UTC, datetime

import httpx
import pytest

from app.metadata.service import MetadataSnapshot
from app.models import FetchStatus
from tests.conftest import TEST_STEAM_ID, load_fixture

OWNED = "/IPlayerService/GetOwnedGames/v1/"
SUMMARIES = "/ISteamUser/GetPlayerSummaries/v2/"


def summaries(visibility: int | None) -> dict:
    players = [] if visibility is None else [{"steamid": TEST_STEAM_ID, "communityvisibilitystate": visibility}]
    return {"response": {"players": players}}


def routes(**by_path):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        result = by_path[request.url.path]
        return result if isinstance(result, httpx.Response) else httpx.Response(200, json=result)

    handler.calls = calls
    return handler


async def test_requires_login(client):
    res = await client.get("/me/library")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_tampered_cookie_is_unauthenticated(client):
    client.cookies.set("sm_session", "forged.token.value")
    res = await client.get("/me/library")
    assert res.status_code == 401


async def test_public_library(client, login, steam_handler):
    handler = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    steam_handler["fn"] = handler
    login()

    res = await client.get("/me/library")

    assert res.status_code == 200
    body = res.json()
    assert body["steamId"] == TEST_STEAM_ID
    assert body["gameCount"] == 4
    # 플레이시간 내림차순, 동점은 appid 오름차순
    assert [g["appid"] for g in body["games"]] == [440, 570, 620, 400]
    tf2 = body["games"][0]
    assert tf2["playtime2Weeks"] == 90
    assert tf2["iconUrl"].endswith("/440/def456.jpg")
    portal = body["games"][3]
    assert portal["lastPlayedAt"] is None and portal["iconUrl"] is None
    assert body["summary"] == {
        "totalPlaytimeMinutes": 5500,
        "playedCount": 3,
        "unplayedCount": 1,
        "recentlyPlayedCount": 1,
    }
    # 세션의 steamId로 조회하고, API 키는 서버에서만 붙는다
    sent = handler.calls[0].url.params
    assert sent["steamid"] == TEST_STEAM_ID
    assert sent["key"] == "test-steam-key-0123456789"
    assert "test-steam-key" not in res.text


@pytest.mark.parametrize(
    ("visibility", "status", "code", "hint"),
    [
        (1, 403, "LIBRARY_PRIVATE", "프로필이 비공개"),
        (3, 403, "LIBRARY_PRIVATE", "게임 세부 정보가 비공개"),
        (None, 404, "PROFILE_NOT_FOUND", "찾을 수 없습니다"),
    ],
)
async def test_empty_response_is_classified(client, login, steam_handler, visibility, status, code, hint):
    steam_handler["fn"] = routes(**{OWNED: {"response": {}}, SUMMARIES: summaries(visibility)})
    login()
    res = await client.get("/me/library")
    assert res.status_code == status
    assert res.json()["error"]["code"] == code
    assert hint in res.json()["error"]["message"]


async def test_zero_games_is_not_private(client, login, steam_handler):
    steam_handler["fn"] = routes(**{OWNED: {"response": {"game_count": 0}}})
    login()
    res = await client.get("/me/library")
    assert res.status_code == 200
    assert res.json()["gameCount"] == 0


@pytest.mark.parametrize(
    ("steam_response", "status", "code"),
    [
        (httpx.Response(429), 503, "STEAM_RATE_LIMITED"),
        (httpx.Response(500), 502, "STEAM_UNAVAILABLE"),
        (httpx.Response(401), 502, "STEAM_UNAVAILABLE"),
        (httpx.Response(200, text="<html>not json</html>"), 502, "STEAM_UNAVAILABLE"),
        (httpx.Response(200, json={"unexpected": True}), 502, "STEAM_UNAVAILABLE"),
        (httpx.Response(200, json={"response": {"games": [{"name": "no appid"}]}}), 502, "STEAM_UNAVAILABLE"),
    ],
)
async def test_steam_failures_map_to_error_codes(client, login, steam_handler, steam_response, status, code):
    steam_handler["fn"] = routes(**{OWNED: steam_response})
    login()
    res = await client.get("/me/library")
    assert res.status_code == status
    assert res.json()["error"]["code"] == code


async def test_timeout_maps_to_steam_timeout(client, login, steam_handler):
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    steam_handler["fn"] = slow
    login()
    res = await client.get("/me/library")
    assert res.status_code == 504
    assert res.json()["error"]["code"] == "STEAM_TIMEOUT"


async def test_library_includes_genres_and_coverage(client, login, steam_handler, fake_metadata):
    t = datetime(2026, 11, 2, tzinfo=UTC)
    fake_metadata.snapshots = {
        440: MetadataSnapshot(440, FetchStatus.SUCCESS, "game", ("Action", "Free To Play"), t),
        620: MetadataSnapshot(620, FetchStatus.TEMPORARY_ERROR),
        400: MetadataSnapshot(400, FetchStatus.NOT_AVAILABLE, "music"),
        # 570: 캐시에 없음 → PENDING
    }
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    login()

    body = (await client.get("/me/library")).json()

    by_id = {g["appid"]: g for g in body["games"]}
    assert by_id[440]["genres"] == ["액션", "무료 플레이"] and by_id[440]["metadataStatus"] == "SUCCESS"
    assert by_id[570]["metadataStatus"] == "PENDING" and by_id[570]["genres"] == []
    assert by_id[400]["appType"] == "music"
    assert by_id[570]["headerImage"] is None  # 메타데이터 수집 전
    assert body["metadataCoverage"] == {
        "success": 1, "pending": 1, "temporaryError": 1, "notAvailable": 1, "total": 4, "ratio": 0.3333,
    }
    assert body["metadataSnapshotAt"].startswith("2026-11-02")
    assert sorted(fake_metadata.requested[0]) == [400, 440, 570, 620]
    # 장르를 아는 게임은 440 하나 → 두 장르가 반씩(동점은 영어 장르명 순)
    assert body["genreDistribution"] == [{"genre": "액션", "share": 0.5}, {"genre": "무료 플레이", "share": 0.5}]


async def test_no_steam_id_parameter_accepted(client, login, steam_handler):
    """다른 사람의 steamId를 쿼리로 넘겨도 무시하고 세션 본인만 조회한다."""
    handler = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    steam_handler["fn"] = handler
    login()
    await client.get("/me/library", params={"steamId": "76561198999999999"})
    assert handler.calls[0].url.params["steamid"] == TEST_STEAM_ID
