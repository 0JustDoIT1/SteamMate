from datetime import UTC, datetime

import httpx
import pytest

from app.deals import DLC_MIN_PLAYTIME_MINUTES, DealItem, dlc_sources, rank_deals
from app.metadata.service import MetadataSnapshot
from app.models import FetchStatus
from app.prices import PriceInfo, PriceSnapshot
from app.steam.web_api import OwnedGame
from tests.conftest import load_fixture
from tests.test_me_library import OWNED, SUMMARIES, routes, summaries

T = datetime(2026, 11, 1, tzinfo=UTC)
WISHLIST = "/IWishlistService/GetWishlist/v1/"


def meta(appid: int, *genres: str, dlc: tuple[int, ...] = (), app_type: str = "game", name: str | None = None):
    return MetadataSnapshot(appid, FetchStatus.SUCCESS, app_type, genres, T, name=name or f"G{appid}", dlc_appids=dlc)


def price(appid: int, discount: int, final: int = 10000) -> PriceSnapshot:
    return PriceSnapshot(appid, FetchStatus.SUCCESS, "KRW", final * 2 if discount else final, final, discount, T)


def wishlist(*appids: int) -> dict:
    return {"response": {"items": [{"appid": a, "priority": i, "date_added": 1} for i, a in enumerate(appids)]}}


def test_dlc_sources_only_from_games_played_three_hours():
    owned = [
        OwnedGame(appid=1, playtime_forever=DLC_MIN_PLAYTIME_MINUTES),
        OwnedGame(appid=2, playtime_forever=DLC_MIN_PLAYTIME_MINUTES - 1),
        OwnedGame(appid=3, playtime_forever=5000),
        OwnedGame(appid=4, playtime_forever=9000),  # 메타데이터 없음
    ]
    metadata = {1: meta(1, dlc=(10, 11)), 2: meta(2, dlc=(20,)), 3: meta(3, dlc=(11, 30))}
    # 11은 1·3 모두의 DLC → 플레이 시간이 긴 3을 본 게임으로
    assert dlc_sources(owned, metadata) == {11: 3, 30: 3, 10: 1}


# --- API ---
# 픽스처 보유 게임: 440(3000분) · 620(1250분) · 570(1250분) · 400(0분)


@pytest.fixture
def owned_meta(fake_metadata):
    fake_metadata.snapshots = {
        440: meta(440, "Action", dlc=(9001, 9002)),
        620: meta(620, "Puzzle", dlc=(9100,)),
        570: meta(570, "Strategy"),
        400: meta(400, "Puzzle", dlc=(9400,)),  # 미플레이 → DLC 제외
    }
    return fake_metadata


async def test_deals_require_login(client):
    assert (await client.get("/me/deals")).status_code == 401


async def test_wishlist_and_dlc_deals(client, login, steam_handler, owned_meta, fake_prices):
    owned_meta.snapshots |= {
        50: meta(50, "Action", name="Wished Action"),
        51: meta(51, "Puzzle", name="Wished Puzzle"),
        9001: meta(9001, app_type="dlc", name="TF2 Pack"),
    }
    fake_prices.snapshots = {
        50: price(50, 40),
        51: price(51, 80),
        52: price(52, 0),  # 위시리스트지만 정가
        9001: price(9001, 25),
        9002: price(9002, 0),
        9100: price(9100, 10),
    }
    handler = routes(**{OWNED: load_fixture("steam/owned_games_public.json"), WISHLIST: wishlist(52, 51, 50)})
    steam_handler["fn"] = handler
    login()

    body = (await client.get("/me/deals")).json()

    assert body["wishlistStatus"] == "OK" and body["wishlistCount"] == 3
    # 취향(Action 가중치 > Puzzle) 일치도 내림차순 → 할인율. 정가(52)는 빠진다
    assert [d["appid"] for d in body["wishlistDeals"]] == [50, 51]
    assert body["wishlistDeals"][0]["name"] == "Wished Action" and body["wishlistDeals"][0]["price"]["discountPercent"] == 40
    dlc = {d["appid"]: d for d in body["dlcDeals"]}
    assert set(dlc) == {9001, 9100}  # 9002 정가, 9400은 미플레이 게임 DLC
    assert dlc[9001]["baseAppid"] == 440 and dlc[9001]["baseName"] == "Team Fortress 2" and dlc[9001]["name"] == "TF2 Pack"
    assert dlc[9100]["name"] == "DLC 9100"  # 이름 수집 전
    assert body["dlcBaseGameCount"] == 2 and body["dlcCheckedCount"] == 3
    assert body["pricePending"] == 0 and body["priceSnapshotAt"].startswith("2026-11-01")
    # 위시리스트는 API 키 없이(공개 범위 존중)
    assert "key" not in next(c for c in handler.calls if c.url.path == WISHLIST).url.params


async def test_empty_or_private_wishlist(client, login, steam_handler, owned_meta):
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json"), WISHLIST: {"response": {}}})
    login()
    body = (await client.get("/me/deals")).json()
    assert body["wishlistStatus"] == "EMPTY_OR_PRIVATE" and body["wishlistDeals"] == []
    # 가격을 아직 모르는 DLC는 수집 중으로 센다(화면이 다시 불러온다)
    assert body["pricePending"] == 3


async def test_wishlist_failure_does_not_fail_deals(client, login, steam_handler, owned_meta):
    steam_handler["fn"] = routes(**{OWNED: load_fixture("steam/owned_games_public.json"), WISHLIST: httpx.Response(503)})
    login()
    res = await client.get("/me/deals")
    assert res.status_code == 200 and res.json()["wishlistStatus"] == "UNAVAILABLE"


async def test_private_library(client, login, steam_handler):
    steam_handler["fn"] = routes(**{OWNED: {"response": {}}, SUMMARIES: summaries(3)})
    login()
    res = await client.get("/me/deals")
    assert res.status_code == 403 and res.json()["error"]["code"] == "LIBRARY_PRIVATE"


def test_dlc_deals_capped_per_base_game():
    def item(appid: int, base: int, affinity: float, discount: int) -> DealItem:
        p = PriceInfo(currency="KRW", initial_price=200, final_price=100, discount_percent=discount)
        return DealItem(appid=appid, name="x", header_image=None, price=p, affinity=affinity, store_url="u", base_appid=base)

    items = [item(a, 1, 0.9, 50) for a in range(10, 15)] + [item(20, 2, 0.5, 90), item(21, 2, 0.5, 10)]
    ranked = rank_deals(items, limit=30, per_base=3)
    # 취향 높은 게임 1의 DLC는 3개까지(할인율 → appid 순), 그다음 게임 2
    assert [d.appid for d in ranked] == [10, 11, 12, 20, 21]
