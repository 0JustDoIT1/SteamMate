from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.chart_queries import PoolEntry, candidate_pool
from app.metadata.service import MetadataSnapshot
from app.models import (
    ChartEntry,
    ChartSnapshot,
    ChartSource,
    FetchStatus,
    SnapshotStatus,
)
from app.prices import PriceSnapshot
from app.recommend import ReasonFactor, RecommendationMode
from app.store_recs import recommend_store
from tests.conftest import load_fixture
from tests.test_me_library import OWNED, routes

GA = RecommendationMode.GENRE_AWARE
PB = RecommendationMode.PLAYTIME_BASED
T = datetime(2026, 11, 1, tzinfo=UTC)
WISHLIST = "/IWishlistService/GetWishlist/v1/"


def meta(appid: int, *genres: str, app_type: str = "game", status=FetchStatus.SUCCESS) -> MetadataSnapshot:
    return MetadataSnapshot(appid, status, app_type, genres, T, name=f"G{appid}", header_image=f"https://img/{appid}")


def price(appid: int, discount: int = 0, final: int = 10000) -> PriceSnapshot:
    initial = final * 100 // (100 - discount) if discount else final
    return PriceSnapshot(appid, FetchStatus.SUCCESS, "KRW", initial, final, discount, T)


def pool(*entries: tuple[int, int, ChartSource]) -> dict[int, PoolEntry]:
    return {a: PoolEntry(a, rank, source, None) for a, rank, source in entries}


PREF = {"RPG": 0.75, "Action": 0.25}
POOL = pool(
    (1, 1, ChartSource.TOP_SELLERS),
    (2, 10, ChartSource.MOST_PLAYED),
    (3, 2, ChartSource.SPECIALS),
    (4, 5, ChartSource.TOP_SELLERS),  # 보유
    (5, 3, ChartSource.TOP_SELLERS),  # DLC
    (6, 4, ChartSource.TOP_SELLERS),  # 메타데이터 수집 전
)
META = {1: meta(1, "Action"), 2: meta(2, "RPG"), 3: meta(3, "RPG", "Action"), 4: meta(4, "RPG"), 5: meta(5, "RPG", app_type="dlc")}
PRICES = {1: price(1), 2: price(2), 3: price(3, discount=50)}


def run(*, mode=GA, on_sale_only=False, wishlist=frozenset(), prices=PRICES, pool_=POOL, metadata=META):
    return recommend_store(
        pool_, frozenset({4}), metadata, prices, PREF,
        mode=mode, on_sale_only=on_sale_only, wishlist=wishlist, coverage_ratio=0.5,
    )


def scores(recs) -> list[tuple[int, float]]:
    return [(r.appid, r.score) for r in recs]


def test_genre_aware_scores():
    recs, count = run()

    # 1: 0.7·0.25 + 0.3·1 = 0.475 / 2: 0.7·0.75 + 0.3·0.1 = 0.555 / 3: 0.7·1.0 + 0.3·0.5 = 0.85
    # 4(보유)·5(DLC)·6(메타데이터 없음)은 후보에서 빠진다
    assert count == 3
    assert scores(recs) == [(3, 0.85), (2, 0.555), (1, 0.475)]
    top = recs[0]
    assert [(r.factor, r.detail) for r in top.reasons] == [
        (ReasonFactor.GENRE_MATCH, "RPG, 액션"),
        (ReasonFactor.POPULAR, "Steam 할인 게임 목록에 오름"),
    ]
    assert recs[1].reasons[1].detail == "주간 접속 순위 10위"
    assert top.price.discount_percent == 50 and top.store_url.endswith("/app/3/")
    for r in recs:
        assert r.score == round(sum(x.contribution for x in r.reasons), 4)


def test_full_price_games_included_and_on_sale_filter():
    assert {r.appid for r in run()[0]} == {1, 2, 3}
    recs, count = run(on_sale_only=True)
    assert count == 1 and [r.appid for r in recs] == [3]


def test_discount_only_breaks_ties():
    p = pool((10, 1, ChartSource.TOP_SELLERS), (11, 1, ChartSource.MOST_PLAYED), (12, 1, ChartSource.CONCURRENT))
    m = {a: meta(a, "RPG") for a in (10, 11, 12)}
    recs, _ = run(pool_=p, metadata=m, prices={10: price(10), 11: price(11, discount=20), 12: price(12, discount=60)})
    # 점수가 같으면 할인율이 큰 게임이 먼저, 그다음 appid
    assert [r.appid for r in recs] == [12, 11, 10]
    assert len({r.score for r in recs}) == 1


def test_price_unknown_still_recommended_but_not_on_sale():
    recs, _ = run(prices={})
    assert {r.appid for r in recs} == {1, 2, 3} and all(r.price is None for r in recs)
    assert run(prices={}, on_sale_only=True) == ([], 0)


def test_playtime_based_uses_popularity_only():
    recs, _ = run(mode=PB)
    assert scores(recs) == [(1, 1.0), (3, 0.5), (2, 0.1)]
    assert recs[0].reasons[-1].factor is ReasonFactor.LOW_GENRE_COVERAGE
    assert not any(r.factor is ReasonFactor.GENRE_MATCH for rec in recs for r in rec.reasons)


def test_wishlisted_flag():
    recs, _ = run(wishlist=frozenset({2}))
    assert {r.appid: r.wishlisted for r in recs} == {3: False, 2: True, 1: False}


def test_same_input_same_result():
    a, _ = run()
    b, _ = recommend_store(
        dict(reversed(list(POOL.items()))), frozenset({4}), META, PRICES, PREF,
        mode=GA, on_sale_only=False, wishlist=frozenset(), coverage_ratio=0.5,
    )
    assert [r.model_dump() for r in a] == [r.model_dump() for r in b]


# --- 후보 풀(DB) ---


async def add_snapshot(sm, source, captured, entries, period=None, status=SnapshotStatus.SUCCESS):
    async with sm() as s:
        snap = ChartSnapshot(source=source, cc="kr", captured_at=captured, period_start=period, status=status)
        snap.entries = [ChartEntry(rank=r, appid=a, name=f"N{a}") for r, a in entries]
        s.add(snap)
        await s.commit()


@pytest.mark.db
async def test_candidate_pool_latest_plus_recent_top_seller_weeks(db_sessionmaker):
    sm = db_sessionmaker
    week = datetime(2026, 10, 27, tzinfo=UTC)
    now = datetime(2026, 11, 3, tzinfo=UTC)
    await add_snapshot(sm, ChartSource.TOP_SELLERS, now, [(1, 100), (2, 101)], period=week)
    for k, appid in ((1, 102), (3, 103), (4, 104)):  # 1·3주 전은 포함, 4주 전은 제외
        await add_snapshot(sm, ChartSource.TOP_SELLERS, now, [(1, appid), (5, 101)], period=week - timedelta(weeks=k))
    await add_snapshot(sm, ChartSource.SPECIALS, now - timedelta(hours=7), [(1, 200)])  # 옛 할인 목록
    await add_snapshot(sm, ChartSource.SPECIALS, now, [(1, 201), (2, 100)])
    await add_snapshot(sm, ChartSource.CONCURRENT, now, [(1, 300)], status=SnapshotStatus.FAILED)

    async with sm() as s:
        got, captured = await candidate_pool(s, "kr")

    assert set(got) == {100, 101, 102, 103, 201}
    assert got[101].best_rank == 2  # 여러 번 오르면 가장 높은 순위
    assert got[100] == PoolEntry(100, 1, ChartSource.TOP_SELLERS, "N100")  # 같은 순위면 판매 순위 먼저
    assert captured == now


@pytest.mark.db
async def test_candidate_pool_empty_before_first_collection(db_sessionmaker):
    async with db_sessionmaker() as s:
        assert await candidate_pool(s, "kr") == ({}, None)


# --- API ---


@pytest.mark.db
async def test_store_recommendations_not_ready(client, login, steam_handler, db_sessionmaker):
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json")})
    login()
    res = await client.get("/me/store-recommendations")
    assert res.status_code == 503 and res.json()["error"]["code"] == "DATA_NOT_READY"


@pytest.mark.db
async def test_store_recommendations_endpoint(client, login, steam_handler, fake_metadata, fake_prices, db_sessionmaker):
    now = datetime.now(UTC)
    # 440은 보유(픽스처), 1·2는 미보유
    await add_snapshot(db_sessionmaker, ChartSource.TOP_SELLERS, now, [(1, 440), (2, 1), (3, 2)], period=now)
    fake_metadata.snapshots = {440: meta(440, "Action"), 1: meta(1, "Action"), 2: meta(2, "RPG")}
    fake_prices.snapshots = {1: price(1, discount=30)}
    wishlist = {"response": {"items": [{"appid": 2, "priority": 1, "date_added": 1}]}}
    handler = routes(**{OWNED: load_fixture("steam/owned_games_public.json"), WISHLIST: wishlist})
    steam_handler["fn"] = handler
    login()

    body = (await client.get("/me/store-recommendations", params={"onSaleOnly": "false"})).json()

    assert body["candidatePoolSize"] == 2 and body["candidateCount"] == 2
    assert [r["appid"] for r in body["recommendations"]] == [1, 2]
    assert body["recommendations"][1]["wishlisted"] is True and body["recommendations"][1]["price"] is None
    assert body["pricePending"] == 1 and body["wishlistChecked"] is True
    assert body["recommendationMode"] == "PLAYTIME_BASED"  # 픽스처 보유 게임 4개 중 1개만 장르 있음
    # 위시리스트는 API 키 없이 조회한다(공개 범위 존중)
    wish_call = next(c for c in handler.calls if c.url.path == WISHLIST)
    assert "key" not in wish_call.url.params
    # 가격은 묶음 수 제한을 지켜 요청한다
    assert fake_prices.requested[0][1] == 3


@pytest.mark.db
async def test_store_recommendations_survive_wishlist_failure(client, login, steam_handler, fake_metadata, db_sessionmaker):
    await add_snapshot(db_sessionmaker, ChartSource.TOP_SELLERS, datetime.now(UTC), [(1, 1)], period=T)
    fake_metadata.snapshots = {1: meta(1, "Action")}
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json"), WISHLIST: httpx.Response(500)})
    login()
    body = (await client.get("/me/store-recommendations")).json()
    assert body["wishlistChecked"] is False and [r["appid"] for r in body["recommendations"]] == [1]


async def test_store_recommendations_invalid_flag(client, login):
    login()
    res = await client.get("/me/store-recommendations", params={"onSaleOnly": "maybe"})
    assert res.status_code == 422
