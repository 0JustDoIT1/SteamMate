"""대시보드 API: 실제 DB에 수집 결과를 넣고 라우터까지 검증한다."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.config import get_settings
from app.dashboard import DashboardService
from app.metadata.service import MetadataSnapshot, Priority
from app.models import FetchStatus
from tests.conftest import TEST_STEAM_ID
from tests.fakes import FakeMetadata
from tests.test_collector import CURRENT_WEEK, T0, Clock, make_collector

pytestmark = pytest.mark.db

GENRES = {
    730: ("Action", "Free To Play"),
    570: ("Action", "Strategy", "Free To Play"),
    440: ("Action", "Free To Play"),
    620: ("Action", "Adventure"),
    578080: ("Action", "Adventure", "Massively Multiplayer"),
}
META = {
    appid: MetadataSnapshot(appid, FetchStatus.SUCCESS, "game", genres, T0, name=f"Meta {appid}")
    for appid, genres in GENRES.items()
}


@pytest.fixture
async def dash_client(db_sessionmaker, steam_handler) -> AsyncIterator[httpx.AsyncClient]:
    get_settings.cache_clear()
    from app.main import create_app

    meta = FakeMetadata(dict(META))
    external = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: steam_handler["fn"](r)))
    app = create_app(
        http=external, metadata=meta, dashboard_service=DashboardService(lambda: db_sessionmaker, meta, cc="kr")
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.app = app
        yield ac
    await external.aclose()


def login(client: httpx.AsyncClient) -> None:
    client.cookies.set("sm_session", client.app.state.sessions.issue(TEST_STEAM_ID))


async def test_not_ready_before_first_collection(dash_client):
    res = await dash_client.get("/steam/dashboard")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "DATA_NOT_READY"


async def test_public_dashboard_sections(dash_client, db_sessionmaker):
    await make_collector(db_sessionmaker, Clock(T0)).run_once()

    body = (await dash_client.get("/steam/dashboard")).json()

    assert body["personalized"] is False
    assert [s["source"] for s in body["sections"]] == [
        "TOP_SELLERS", "MOST_PLAYED", "CONCURRENT", "SPECIALS", "NEW_RELEASES",
    ]
    top = body["sections"][0]
    assert top["periodStart"].startswith("2026-10-")
    cs2, dota, new_hit = top["entries"]
    assert (cs2["rankDelta"], cs2["isNew"]) == (1, False)  # 2위 → 1위
    assert (dota["rankDelta"], dota["isNew"]) == (-1, False)
    assert (new_hit["rankDelta"], new_hit["isNew"]) == (None, True)
    assert cs2["genres"] == ["액션", "무료 플레이"] and new_hit["genres"] == []  # 응답은 한국어 표시명
    assert cs2["owned"] is None and cs2["affinity"] is None

    most_played = body["sections"][1]["entries"]
    assert most_played[1]["name"] == "Meta 440"  # 이름 없는 소스는 메타데이터 이름 사용

    concurrent = body["sections"][2]["entries"]
    assert concurrent[0]["rankDelta"] is None and concurrent[0]["isNew"] is False  # 비주간 소스

    specials = body["sections"][3]["entries"]
    assert (specials[0]["discountPercent"], specials[0]["finalPrice"]) == (75, 275000)

    dist = body["genreDistribution"]
    assert dist["basedOn"] == 4 and dist["withGenres"] == 3  # 730·570·999001·440 중 999001은 장르 미상
    assert dist["genres"][0] == {"genre": "액션", "count": 3}


async def test_failed_source_section_is_hidden(dash_client, db_sessionmaker):
    bad = {"/ISteamChartsService/GetGamesByConcurrentPlayers/v1/": httpx.Response(503)}
    await make_collector(db_sessionmaker, Clock(T0), overrides=bad).run_once()

    body = (await dash_client.get("/steam/dashboard")).json()
    assert "CONCURRENT" not in [s["source"] for s in body["sections"]]


async def test_logged_in_dashboard_marks_owned_and_affinity(dash_client, db_sessionmaker, steam_handler):
    await make_collector(db_sessionmaker, Clock(T0)).run_once()
    owned = {"response": {"game_count": 2, "games": [
        {"appid": 570, "playtime_forever": 6000},  # Action·Strategy·F2P
        {"appid": 620, "playtime_forever": 600},  # Action·Adventure
    ]}}
    calls: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["steamid"])
        return httpx.Response(200, json=owned)

    steam_handler["fn"] = handler
    login(dash_client)

    body = (await dash_client.get("/steam/dashboard")).json()
    await dash_client.get("/steam/dashboard")

    assert body["personalized"] is True
    top = {e["appid"]: e for e in body["sections"][0]["entries"]}
    assert top[570]["owned"] is True and top[730]["owned"] is False
    assert 0 < top[730]["affinity"] <= 1
    assert top[999001]["affinity"] is None  # 장르를 모르면 매칭도 없음
    assert calls == [TEST_STEAM_ID]  # 보유 목록은 5분 메모리 캐시


async def test_private_library_falls_back_to_public_dashboard(dash_client, db_sessionmaker, steam_handler):
    await make_collector(db_sessionmaker, Clock(T0)).run_once()
    steam_handler["fn"] = lambda r: httpx.Response(200, json={"response": {}})
    login(dash_client)
    res = await dash_client.get("/steam/dashboard")
    assert res.status_code == 200 and res.json()["personalized"] is False


async def test_steam_error_falls_back_to_public_dashboard(dash_client, db_sessionmaker, steam_handler):
    await make_collector(db_sessionmaker, Clock(T0)).run_once()
    steam_handler["fn"] = lambda r: httpx.Response(500)
    login(dash_client)
    res = await dash_client.get("/steam/dashboard")
    assert res.status_code == 200 and res.json()["personalized"] is False


async def test_dashboard_reads_latest_success_snapshot(dash_client, db_sessionmaker):
    clock = Clock(T0)
    await make_collector(db_sessionmaker, clock).run_once()
    clock.now = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
    newer = {"/api/featuredcategories": {
        "specials": {"items": [{"id": 1091500, "type": 0, "name": "Cyberpunk 2077", "discount_percent": 60,
                                 "final_price": 2640000, "original_price": 6600000, "currency": "KRW"}]},
        "new_releases": {"items": [{"id": 999002, "type": 0, "name": "Fresh Game"}]},
    }}
    await make_collector(db_sessionmaker, clock, overrides=newer).run_once()

    body = (await dash_client.get("/steam/dashboard")).json()
    specials = next(s for s in body["sections"] if s["source"] == "SPECIALS")
    assert [e["appid"] for e in specials["entries"]] == [1091500]
    assert specials["snapshotAt"].startswith("2026-11-03T18:00")


async def test_current_week_is_latest_period_after_backfill(dash_client, db_sessionmaker):
    """회귀: 백필한 과거 주가 id가 더 커도 '이번 주'는 집계 주가 가장 늦은 스냅샷이어야 한다."""
    await make_collector(db_sessionmaker, Clock(T0), history=True).run_once()

    body = (await dash_client.get("/steam/dashboard")).json()
    top = body["sections"][0]
    assert top["source"] == "TOP_SELLERS"
    assert top["periodStart"].startswith(datetime.fromtimestamp(CURRENT_WEEK, UTC).date().isoformat())
    assert [e["appid"] for e in top["entries"]] == [730, 570, 999001]


async def test_month_and_year_aggregate_weekly_points(dash_client, db_sessionmaker):
    await make_collector(db_sessionmaker, Clock(T0), history=True).run_once()

    body = (await dash_client.get("/steam/dashboard")).json()
    periods = {p["period"]: p for p in body["sections"][0]["periods"]}

    month = periods["MONTH"]
    assert (month["weeksIncluded"], month["weeksRequired"]) == (4, 4)
    # 주마다 순위가 1→2→3으로 순환: 730 = 100+99+98+100, 570 = 99+98+100+99, 999001 = 98+100+99+98
    assert [(e["appid"], e["score"], e["weeksCharted"], e["bestRank"]) for e in month["entries"]] == [
        (730, 397, 4, 1), (570, 396, 4, 1), (999001, 395, 4, 1),
    ]
    assert month["entries"][0]["rank"] == 1 and month["entries"][0]["rankDelta"] is None

    year = periods["YEAR"]
    assert year["weeksRequired"] == 52 and year["weeksIncluded"] >= 50

    # 최다 플레이는 Steam이 과거 기록을 주지 않아 기간 집계를 하지 않는다(주간만)
    assert body["sections"][1]["source"] == "MOST_PLAYED" and body["sections"][1]["periods"] == []
    # 기간 집계가 없는 섹션
    assert body["sections"][2]["periods"] == []


async def test_metadata_header_image_preferred_over_guessed(dash_client, db_sessionmaker):
    await make_collector(db_sessionmaker, Clock(T0)).run_once()
    meta = dash_client.app.state.metadata
    meta.snapshots[730] = MetadataSnapshot(
        730, FetchStatus.SUCCESS, "game", GENRES[730], T0, name="CS2", header_image="https://cdn.example/730/h.jpg"
    )
    body = (await dash_client.get("/steam/dashboard")).json()
    cs2 = body["sections"][0]["entries"][0]
    assert cs2["imageUrl"] == "https://cdn.example/730/h.jpg"
    dota = body["sections"][0]["entries"][1]
    assert dota["imageUrl"].endswith("/apps/570/header.jpg")  # 정확한 주소가 없으면 추정 주소


async def test_displayed_games_requested_high_priority(dash_client, db_sessionmaker):
    await make_collector(db_sessionmaker, Clock(T0)).run_once()
    meta = dash_client.app.state.metadata
    meta.priorities.clear()
    await dash_client.get("/steam/dashboard")
    assert meta.priorities[0] is Priority.HIGH


async def test_public_part_is_cached_briefly(db_sessionmaker):
    clock = {"t": 0.0}
    meta = FakeMetadata(dict(META))
    service = DashboardService(lambda: db_sessionmaker, meta, cc="kr", cache_seconds=120, clock=lambda: clock["t"])
    await make_collector(db_sessionmaker, Clock(T0)).run_once()
    first = await service.build(None)

    later = Clock(T0 + timedelta(hours=6))
    newer = {"/api/featuredcategories": {
        "specials": {"items": [{"id": 1091500, "type": 0, "name": "Cyberpunk 2077", "discount_percent": 60}]},
        "new_releases": {"items": [{"id": 999002, "type": 0, "name": "Fresh Game"}]},
    }}
    await make_collector(db_sessionmaker, later, overrides=newer).run_once()

    assert await service.build(None) == first  # 캐시 유효 시간 안: 같은 내용
    clock["t"] = 121
    refreshed = await service.build(None)
    specials = next(s for s in refreshed.sections if s.source.value == "SPECIALS")
    assert [e.appid for e in specials.entries] == [1091500]


async def test_sales_trend_is_last_12_weeks_oldest_first(dash_client, db_sessionmaker):
    await make_collector(db_sessionmaker, Clock(T0), history=True).run_once()

    top = (await dash_client.get("/steam/dashboard")).json()["sections"][0]

    times = top["trendTimes"]
    assert len(times) == 12 and times == sorted(times)
    assert times[-1].startswith(datetime.fromtimestamp(CURRENT_WEEK, UTC).date().isoformat())
    cs2 = next(e for e in top["entries"] if e["appid"] == 730)
    # fixture는 주마다 순위가 1→2→3 순환: k주 전 순위 = 1 + k % 3 (오래된 것 → 최신)
    assert cs2["trend"] == [1 + k % 3 for k in range(11, -1, -1)]
    month = next(p for p in top["periods"] if p["period"] == "MONTH")
    assert len(month["entries"][0]["trend"]) == 12  # 합산 순위에도 같은 축의 추이


async def test_concurrent_trend_buckets_and_24h_peak(dash_client, db_sessionmaker):
    # 1시간마다 수집 6회: 접속자를 바꿔 가며 저장
    for h in range(6):
        body = {"response": {"ranks": [
            {"rank": 1, "appid": 730, "concurrent_in_game": 1000 + h * 100},
            {"rank": 2, "appid": 578080, "concurrent_in_game": 500},
        ]}}
        overrides = {"/ISteamChartsService/GetGamesByConcurrentPlayers/v1/": body}
        await make_collector(db_sessionmaker, Clock(T0 + timedelta(hours=h)), overrides=overrides).run_once()

    sec = next(s for s in (await dash_client.get("/steam/dashboard")).json()["sections"] if s["source"] == "CONCURRENT")

    # 12:00~17:00 수집 → 3시간 구간 2개(12~15시, 15~18시), 구간마다 가장 늦은 수집본
    assert len(sec["trendTimes"]) == 2
    cs2 = sec["entries"][0]
    assert cs2["trend"] == [1200, 1500]
    assert cs2["dayPeak"] == 1500
    other = sec["entries"][1]
    assert other["trend"] == [500, 500]


async def test_sections_without_trend(dash_client, db_sessionmaker):
    await make_collector(db_sessionmaker, Clock(T0)).run_once()
    body = (await dash_client.get("/steam/dashboard")).json()
    for s in body["sections"]:
        if s["source"] in ("MOST_PLAYED", "SPECIALS", "NEW_RELEASES"):
            assert s["trendTimes"] == [] and all(e["trend"] is None for e in s["entries"])
