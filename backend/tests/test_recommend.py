import random
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.metadata.coverage import MetadataCoverage
from app.metadata.service import MetadataSnapshot
from app.models import FetchStatus
from app.recommend import ReasonFactor, RecommendationMode, choose_mode, recommend
from app.steam.web_api import OwnedGame
from tests.conftest import load_fixture
from tests.test_me_library import OWNED, SUMMARIES, routes, summaries

NOW = datetime(2026, 11, 3, tzinfo=UTC)
T = datetime(2026, 11, 1, tzinfo=UTC)
GA = RecommendationMode.GENRE_AWARE
PB = RecommendationMode.PLAYTIME_BASED


def game(appid: int, minutes: int, *, recent: int = 0, days_ago: int | None = None) -> OwnedGame:
    played = int((NOW - timedelta(days=days_ago)).timestamp()) if days_ago is not None else 0
    return OwnedGame(appid=appid, name=f"G{appid}", playtime_forever=minutes, playtime_2weeks=recent, rtime_last_played=played)


def meta(appid: int, *genres: str, app_type: str = "game") -> MetadataSnapshot:
    return MetadataSnapshot(appid, FetchStatus.SUCCESS, app_type, genres, T, header_image=f"https://img/{appid}.jpg")


def run(owned, snapshots, *, mode=GA, prefer=False, exclude=frozenset(), ratio=1.0):
    return recommend(
        owned, snapshots, mode=mode, prefer_unplayed=prefer, exclude=exclude, coverage_ratio=ratio, now=NOW
    )


# 취향: 1(600분)·4(60분)가 모두 RPG → RPG 가중치 1.0
OWNED_GAMES = [game(1, 600), game(2, 0), game(3, 0), game(4, 60), game(5, 200), game(6, 0)]
SNAPSHOTS = {
    1: meta(1, "RPG"),
    2: meta(2, "RPG"),
    3: meta(3, "Action"),
    4: meta(4, "RPG"),
    5: meta(5, "RPG"),
    6: meta(6, "RPG", app_type="dlc"),
}


def scores(recs) -> list[tuple[int, float]]:
    return [(r.appid, r.score) for r in recs]


def test_genre_aware_scores_and_reasons():
    recs, candidates = run(OWNED_GAMES, SNAPSHOTS)

    # 후보: 2시간 미만이면서 게임인 2·3·4 (1·5는 2시간 이상, 6은 DLC)
    assert candidates == 3
    assert scores(recs) == [(2, 0.9), (4, 0.75), (3, 0.3)]
    top = recs[0]
    assert [(r.factor, r.detail, r.contribution) for r in top.reasons] == [
        (ReasonFactor.GENRE_MATCH, "RPG", 0.6),
        (ReasonFactor.UNPLAYED, "미플레이", 0.3),
    ]
    assert recs[1].reasons[1].detail == "60분 플레이"
    assert top.header_image == "https://img/2.jpg"
    for r in recs:
        assert r.score == round(sum(x.contribution for x in r.reasons), 4)


def test_prefer_unplayed_raises_unplayed_weight():
    recs, _ = run(OWNED_GAMES, SNAPSHOTS, prefer=True)
    assert scores(recs) == [(2, 0.95), (4, 0.7), (3, 0.5)]


def test_recent_genre_uses_two_week_playtime():
    owned = [game(1, 600), game(7, 300, recent=120), game(2, 0), game(3, 0)]
    snaps = {1: meta(1, "RPG"), 7: meta(7, "Action"), 2: meta(2, "RPG"), 3: meta(3, "Action")}

    recs, _ = run(owned, snaps)

    by_id = {r.appid: r for r in recs}
    recent = [r for r in by_id[3].reasons if r.factor is ReasonFactor.RECENT_GENRE]
    assert recent and recent[0].detail == "액션" and recent[0].contribution == 0.1
    assert not any(r.factor is ReasonFactor.RECENT_GENRE for r in by_id[2].reasons)


def test_ties_break_by_appid():
    owned = [game(30, 0), game(10, 0), game(20, 0)]
    recs, _ = run(owned, {a: meta(a, "Indie") for a in (10, 20, 30)})
    assert [r.appid for r in recs] == [10, 20, 30]


def test_exclude_and_unknown_metadata():
    owned = [game(2, 0), game(8, 0), game(9, 30)]
    # 8은 메타데이터 수집 전(종류 모름) → 후보로 둔다
    recs, candidates = run(owned, {2: meta(2, "RPG"), 9: meta(9, "RPG")}, exclude=frozenset({2}))
    assert candidates == 2
    assert {r.appid for r in recs} == {8, 9}
    assert next(r for r in recs if r.appid == 8).genres == []


def test_playtime_based_uses_recent_launch_and_notes_low_coverage():
    owned = [game(1, 0), game(2, 30, days_ago=10), game(3, 60, days_ago=200)]
    recs, candidates = run(owned, {}, mode=PB, ratio=0.42)

    # 미플레이(1)는 순서 근거가 없어 후보에서 빠진다
    # 2: 0.7·0.75 + 0.3 = 0.825 / 3: 0.7·0.5 = 0.35 (90일 넘음)
    assert candidates == 2
    assert scores(recs) == [(2, 0.825), (3, 0.35)]
    factors = [r.factor for r in recs[0].reasons]
    assert factors == [ReasonFactor.UNPLAYED, ReasonFactor.RECENTLY_PLAYED, ReasonFactor.LOW_GENRE_COVERAGE]
    assert recs[0].reasons[1].detail == "10일 전 실행"
    note = recs[0].reasons[-1]
    assert note.contribution == 0 and "42%" in note.detail
    assert not any(r.factor is ReasonFactor.GENRE_MATCH for rec in recs for r in rec.reasons)


def test_playtime_based_ignores_prefer_unplayed():
    owned = [game(1, 0), game(2, 30, days_ago=10)]
    with_prefer, _ = run(owned, {}, mode=PB, prefer=True)
    without, _ = run(owned, {}, mode=PB, prefer=False)
    assert scores(with_prefer) == scores(without) == [(2, 0.825)]


def test_same_input_gives_same_result_regardless_of_order():
    """PRD 재현성: 같은 입력·같은 메타데이터면 같은 추천(입력 순서와 무관)."""
    first, _ = run(OWNED_GAMES, SNAPSHOTS)
    shuffled = OWNED_GAMES[:]
    random.Random(7).shuffle(shuffled)
    second, _ = run(shuffled, dict(reversed(list(SNAPSHOTS.items()))))
    assert [r.model_dump() for r in first] == [r.model_dump() for r in second]


def test_no_candidates():
    recs, candidates = run([game(1, 600)], {1: meta(1, "RPG")})
    assert recs == [] and candidates == 0


@pytest.mark.parametrize(("ratio", "mode"), [(0.9, GA), (0.8999, PB), (0.0, PB)])
def test_mode_threshold(ratio, mode):
    coverage = MetadataCoverage(success=0, pending=0, temporary_error=0, not_available=0, total=0, ratio=ratio)
    assert choose_mode(coverage, 0.9) is mode


# --- API ---


async def test_recommendations_require_login(client):
    res = await client.get("/me/recommendations")
    assert res.status_code == 401


async def test_recommendations_endpoint(client, login, steam_handler, fake_metadata):
    # 픽스처: 440(3000분)·620(1250분)·570(1250분)·400(0분)
    fake_metadata.snapshots = {
        440: meta(440, "Action"),
        620: meta(620, "Adventure"),
        570: meta(570, "Action"),
        400: meta(400, "Adventure"),
    }
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    login()

    res = await client.get("/me/recommendations", params={"preferUnplayed": "true"})

    assert res.status_code == 200
    body = res.json()
    assert body["recommendationMode"] == "GENRE_AWARE"
    assert body["preferUnplayed"] is True
    assert body["candidateCount"] == 1 and body["excludedCount"] == 0
    rec = body["recommendations"][0]
    assert rec["appid"] == 400 and rec["genres"] == ["어드벤처"]
    assert rec["reasons"][0] == {"factor": "UNPLAYED", "detail": "미플레이", "contribution": 0.5}
    assert body["metadataCoverage"]["ratio"] == 1.0
    assert body["metadataSnapshotAt"].startswith("2026-11-01")
    assert body["calculatedAt"]


async def test_recommendations_exclude_and_low_coverage(client, login, steam_handler):
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    login()

    res = await client.get("/me/recommendations", params=[("exclude", "400"), ("exclude", "999")])

    body = res.json()
    # 메타데이터가 없으니 수집률 0 → 플레이시간 기반, 유일한 후보 400은 제외됨
    assert body["recommendationMode"] == "PLAYTIME_BASED"
    assert body["recommendations"] == [] and body["candidateCount"] == 0
    assert body["excludedCount"] == 1


@pytest.mark.parametrize("params", [{"exclude": "abc"}, {"exclude": "0"}, {"preferUnplayed": "maybe"}])
async def test_recommendations_invalid_input(client, login, steam_handler, params):
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    login()
    res = await client.get("/me/recommendations", params=params)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_INPUT"


async def test_recommendations_reject_huge_exclude_list(client, login, steam_handler):
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    login()
    res = await client.get("/me/recommendations", params=[("exclude", str(i)) for i in range(1, 1002)])
    assert res.status_code == 422


async def test_recommendations_private_library(client, login, steam_handler):
    steam_handler["fn"] = routes(**{OWNED: {"response": {}}, SUMMARIES: summaries(3)})
    login()
    res = await client.get("/me/recommendations")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "LIBRARY_PRIVATE"


async def test_steam_error_propagates(client, login, steam_handler):
    steam_handler["fn"] = routes(**{OWNED: httpx.Response(429)})
    login()
    res = await client.get("/me/recommendations")
    assert res.json()["error"]["code"] == "STEAM_RATE_LIMITED"
