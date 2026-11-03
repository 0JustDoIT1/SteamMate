"""할인(F4ⓐⓑ): 위시리스트 할인, 보유 게임 DLC 할인. 위시리스트·보유 목록은 저장하지 않는다.

- 위시리스트: 본인 공개 위시리스트를 요청할 때만 조회. 비어 있음과 비공개를 구분할 수 없어 함께 안내한다.
- DLC: 2시간 이상 플레이한 보유 게임의 DLC(사용자 결정). DLC 보유 여부는 Steam이 알려 주지 않아 "미확인"이다.
- 가격은 한 요청에 묶음 수 제한(max_batches)이 있어 처음에는 일부만 나올 수 있다(price_pending → 화면 폴링).
- 정렬: 취향 일치도 내림차순 → 할인율 내림차순 → appid (PRD). DLC 취향은 본 게임 장르로 계산한다.
"""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum

from app.library import load_owned_games
from app.metadata.service import MetadataLookup, MetadataSnapshot, Priority
from app.models import FetchStatus
from app.owned_cache import OwnedGamesCache
from app.prices import PriceInfo, PriceLookup, PriceSnapshot, latest_fetch, price_info
from app.schemas import CamelModel
from app.steam.web_api import OwnedGame, SteamWebApi
from app.store_recs import STORE_URL, wishlist_ids
from app.taste import affinity, genre_preference

DLC_MIN_PLAYTIME_MINUTES = 120
MAX_DLC_DEALS = 30
# DLC는 본 게임 취향으로 정렬해 같은 게임의 DLC가 모두 같은 점수가 된다 → 한 게임이 목록을 채우지 않게 제한
MAX_DLC_PER_GAME = 3


class WishlistStatus(StrEnum):
    OK = "OK"
    EMPTY_OR_PRIVATE = "EMPTY_OR_PRIVATE"
    UNAVAILABLE = "UNAVAILABLE"  # Steam 오류(할인 화면 전체를 실패시키지 않는다)


class DealItem(CamelModel):
    appid: int
    name: str
    header_image: str | None
    price: PriceInfo
    # 내 장르 취향과의 일치도(0~1). 장르를 모르면 None
    affinity: float | None
    store_url: str
    # DLC만: 본 게임
    base_appid: int | None = None
    base_name: str | None = None


class DealsResponse(CamelModel):
    wishlist_deals: list[DealItem]
    wishlist_status: WishlistStatus
    wishlist_count: int
    # 본 게임당 최대 3개, 전체 최대 30개
    dlc_deals: list[DealItem]
    # DLC를 확인한 보유 게임 수(2시간 이상 플레이 + 장르 정보 있음) / 확인한 DLC 수
    dlc_base_game_count: int
    dlc_checked_count: int
    # 가격을 아직 모르는 대상 수(수집 중이면 화면이 다시 불러온다)
    price_pending: int
    price_snapshot_at: datetime | None
    calculated_at: datetime


def dlc_sources(owned: list[OwnedGame], metadata: Mapping[int, MetadataSnapshot]) -> dict[int, int]:
    """DLC appid → 본 게임 appid. 여러 게임이 같은 DLC를 가지면 플레이 시간이 긴 게임을 본 게임으로 본다."""
    sources: dict[int, int] = {}
    for game in sorted(owned, key=lambda g: (-g.playtime_forever, g.appid)):
        meta = metadata.get(game.appid)
        if game.playtime_forever < DLC_MIN_PLAYTIME_MINUTES or meta is None or meta.status is not FetchStatus.SUCCESS:
            continue
        for dlc in meta.dlc_appids:
            sources.setdefault(dlc, game.appid)
    return sources


def rank_deals(items: list[DealItem], limit: int | None = None, per_base: int | None = None) -> list[DealItem]:
    ordered = sorted(
        items, key=lambda d: (-(d.affinity if d.affinity is not None else -1), -d.price.discount_percent, d.appid)
    )
    if per_base is not None:
        taken: dict[int | None, int] = {}
        kept = []
        for d in ordered:
            if taken.get(d.base_appid, 0) < per_base:
                taken[d.base_appid] = taken.get(d.base_appid, 0) + 1
                kept.append(d)
        ordered = kept
    return ordered[:limit] if limit is not None else ordered


def build_deal(
    appid: int,
    price: PriceSnapshot,
    meta: MetadataSnapshot | None,
    genres_for_affinity: tuple[str, ...] | None,
    preference: Mapping[str, float],
    *,
    base: tuple[int, str] | None = None,
    fallback_name: Callable[[int], str] = lambda a: f"App {a}",
) -> DealItem | None:
    info = price_info(price)
    if info is None or info.discount_percent <= 0:
        return None
    return DealItem(
        appid=appid,
        name=(meta.name if meta and meta.name else None) or fallback_name(appid),
        header_image=meta.header_image if meta else None,
        price=info,
        affinity=affinity(preference, genres_for_affinity) if genres_for_affinity and preference else None,
        store_url=STORE_URL.format(appid=appid),
        base_appid=base[0] if base else None,
        base_name=base[1] if base else None,
    )


async def fetch_deals(
    api: SteamWebApi,
    metadata: MetadataLookup,
    prices: PriceLookup,
    owned_cache: OwnedGamesCache,
    steam_id: str,
    *,
    max_price_batches: int,
) -> DealsResponse:
    owned = await load_owned_games(api, owned_cache, steam_id)
    owned_meta = await metadata.lookup((g.appid for g in owned), Priority.HIGH)
    genres_by_appid = {a: s.genres for a, s in owned_meta.items() if s.status is FetchStatus.SUCCESS}
    preference = genre_preference(((g.appid, g.playtime_forever) for g in owned), genres_by_appid)

    wishlist = await wishlist_ids(api, steam_id)
    wish = sorted(wishlist or ())
    dlc_base = dlc_sources(owned, owned_meta)

    # 위시리스트를 먼저 받는다(사용자가 직접 고른 게임이라 우선).
    all_prices = await prices.lookup([*wish, *dlc_base], max_batches=max_price_batches)

    on_sale = [a for a in wish if all_prices[a].on_sale]
    dlc_on_sale = [a for a in dlc_base if all_prices[a].on_sale]
    # 이름·이미지·장르는 할인 중인 것만 조회한다(DLC 수천 개를 모두 조회하지 않기 위해).
    sale_meta = await metadata.lookup([*on_sale, *dlc_on_sale], Priority.HIGH)
    names = {g.appid: g.name for g in owned}

    wishlist_deals = [
        d
        for a in on_sale
        if (
            d := build_deal(
                a,
                all_prices[a],
                sale_meta.get(a),
                _genres(sale_meta.get(a)),
                preference,
            )
        )
    ]
    dlc_deals = [
        d
        for a in dlc_on_sale
        if (
            d := build_deal(
                a,
                all_prices[a],
                sale_meta.get(a),
                genres_by_appid.get(dlc_base[a]),
                preference,
                base=(dlc_base[a], names.get(dlc_base[a]) or f"App {dlc_base[a]}"),
                fallback_name=lambda x: f"DLC {x}",
            )
        )
    ]
    considered = [*wish, *dlc_base]
    if wishlist is None:
        status = WishlistStatus.UNAVAILABLE
    elif wish:
        status = WishlistStatus.OK
    else:
        status = WishlistStatus.EMPTY_OR_PRIVATE
    return DealsResponse(
        wishlist_deals=rank_deals(wishlist_deals),
        wishlist_status=status,
        wishlist_count=len(wish),
        dlc_deals=rank_deals(dlc_deals, MAX_DLC_DEALS, per_base=MAX_DLC_PER_GAME),
        dlc_base_game_count=len(set(dlc_base.values())),
        dlc_checked_count=len(dlc_base),
        price_pending=sum(1 for a in considered if all_prices[a].status is FetchStatus.PENDING),
        price_snapshot_at=latest_fetch(all_prices[a] for a in considered),
        calculated_at=datetime.now(UTC),
    )


def _genres(meta: MetadataSnapshot | None) -> tuple[str, ...] | None:
    return meta.genres if meta and meta.status is FetchStatus.SUCCESS else None

