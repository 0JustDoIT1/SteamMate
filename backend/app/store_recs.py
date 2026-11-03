"""미보유 게임 추천(F4ⓒ, "살 만한 게임"). 정가 게임 포함, "할인 중만 보기" 필터 제공.

후보 = 대시보드 최신 목록 + 최근 4주 판매 순위 − 보유 게임, 게임으로 확인되고 장르가 있는 것만.
점수 = 0.7·genreMatch + 0.3·popularity (사용자 결정, DEVLOG 5단계). 할인은 점수에 넣지 않고 동점 정렬·표시·필터에만 쓴다.
장르 수집률이 낮으면(PLAYTIME_BASED) 취향이 불완전하므로 인기만으로 정하고 그 사실을 이유에 적는다.
점수 계산은 순수 함수라 같은 입력이면 같은 결과가 나온다.
"""

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chart_queries import PoolEntry, candidate_pool
from app.errors import AppError, ErrorCode
from app.genre_labels import korean_genre
from app.library import load_owned_games
from app.metadata.coverage import MetadataCoverage, compute_coverage
from app.metadata.service import MetadataLookup, MetadataSnapshot, Priority
from app.models import ChartSource, FetchStatus
from app.owned_cache import OwnedGamesCache
from app.prices import PriceInfo, PriceLookup, PriceSnapshot, latest_fetch, price_info
from app.recommend import Reason, ReasonFactor, RecommendationMode, choose_mode
from app.schemas import CamelModel
from app.steam.web_api import SteamWebApi
from app.taste import affinity, genre_preference

logger = logging.getLogger(__name__)

TOP_N = 10
STORE_URL = "https://store.steampowered.com/app/{appid}/"

WEIGHTS: dict[RecommendationMode, dict[ReasonFactor, float]] = {
    RecommendationMode.GENRE_AWARE: {ReasonFactor.GENRE_MATCH: 0.7, ReasonFactor.POPULAR: 0.3},
    RecommendationMode.PLAYTIME_BASED: {ReasonFactor.POPULAR: 1.0},
}

# 화면의 대시보드 탭 이름과 맞춘다. 할인·신작은 순위가 아니라 상점 기획 목록이다.
SOURCE_LABEL = {
    ChartSource.TOP_SELLERS: "판매 순위",
    ChartSource.MOST_PLAYED: "주간 접속 순위",
    ChartSource.CONCURRENT: "실시간 접속 순위",
    ChartSource.SPECIALS: "할인 게임 목록",
    ChartSource.NEW_RELEASES: "신작 게임 목록",
}
RANKED = (ChartSource.TOP_SELLERS, ChartSource.MOST_PLAYED, ChartSource.CONCURRENT)


class StoreRecommendation(CamelModel):
    appid: int
    name: str
    score: float
    genres: list[str]
    header_image: str | None
    price: PriceInfo | None  # 없으면 무료·미출시·가격 수집 전
    wishlisted: bool
    store_url: str
    reasons: list[Reason]


class StoreRecommendationsResponse(CamelModel):
    recommendations: list[StoreRecommendation]
    # 후보 풀(보유 게임 제외) / 그중 조건(게임·장르 확인, 할인 필터)을 통과한 수
    candidate_pool_size: int
    candidate_count: int
    # 장르·가격을 아직 모르는 후보 수(수집 중이면 화면이 다시 불러온다)
    metadata_pending: int
    price_pending: int
    on_sale_only: bool
    wishlist_checked: bool
    recommendation_mode: RecommendationMode
    metadata_coverage: MetadataCoverage
    pool_snapshot_at: datetime | None
    price_snapshot_at: datetime | None
    calculated_at: datetime


def recommend_store(
    pool: Mapping[int, PoolEntry],
    owned: frozenset[int],
    metadata: Mapping[int, MetadataSnapshot],
    prices: Mapping[int, PriceSnapshot],
    preference: Mapping[str, float],
    *,
    mode: RecommendationMode,
    on_sale_only: bool,
    wishlist: frozenset[int],
    coverage_ratio: float,
    genre_label: Callable[[str], str] = korean_genre,
    limit: int = TOP_N,
) -> tuple[list[StoreRecommendation], int]:
    """(TOP N, 조건 통과 후보 수). 정렬: 점수 내림차순 → 할인율 내림차순 → appid 오름차순."""
    weights = WEIGHTS[mode]
    scored: list[tuple[StoreRecommendation, int]] = []
    for appid, entry in pool.items():
        meta = metadata.get(appid)
        if appid in owned or meta is None or meta.status is not FetchStatus.SUCCESS or meta.app_type != "game":
            continue
        price = prices.get(appid)
        if on_sale_only and not (price and price.on_sale):
            continue
        values: dict[ReasonFactor, tuple[float, str | None]] = {
            ReasonFactor.POPULAR: (1 / entry.best_rank, _popular_detail(entry)),
        }
        if mode is RecommendationMode.GENRE_AWARE:
            values[ReasonFactor.GENRE_MATCH] = (affinity(preference, meta.genres), _top_genres(preference, meta.genres, genre_label))
        reasons = [
            Reason(factor=f, detail=values[f][1], contribution=round(w * values[f][0], 4)) for f, w in weights.items()
        ]
        reasons = sorted((r for r in reasons if r.contribution > 0), key=lambda r: -r.contribution)
        score = round(sum(r.contribution for r in reasons), 4)
        if mode is RecommendationMode.PLAYTIME_BASED:
            reasons.append(
                Reason(
                    factor=ReasonFactor.LOW_GENRE_COVERAGE,
                    detail=f"내 장르 정보 수집 중({coverage_ratio:.0%}) — 인기 순으로 추천",
                    contribution=0.0,
                )
            )
        rec = StoreRecommendation(
            appid=appid,
            name=meta.name or entry.name or f"App {appid}",
            score=score,
            genres=[genre_label(g) for g in meta.genres],
            header_image=meta.header_image,
            price=price_info(price),
            wishlisted=appid in wishlist,
            store_url=STORE_URL.format(appid=appid),
            reasons=reasons,
        )
        scored.append((rec, (price.discount_percent or 0) if price and price.on_sale else 0))
    scored.sort(key=lambda x: (-x[0].score, -x[1], x[0].appid))
    return [rec for rec, _ in scored[:limit]], len(scored)


def _popular_detail(entry: PoolEntry) -> str:
    label = SOURCE_LABEL[entry.source]
    return f"{label} {entry.best_rank}위" if entry.source in RANKED else f"Steam {label}"


def _top_genres(preference: Mapping[str, float], genres, label: Callable[[str], str], n: int = 2) -> str | None:
    matched = sorted((g for g in set(genres) if preference.get(g, 0) > 0), key=lambda g: (-preference[g], g))
    return ", ".join(label(g) for g in matched[:n]) or None


async def wishlist_ids(api: SteamWebApi, steam_id: str) -> frozenset[int] | None:
    """위시리스트 appid. Steam 오류면 None(추천은 위시리스트 표시 없이 계속한다)."""
    try:
        items = await api.get_wishlist(steam_id)
    except AppError as exc:
        logger.info("wishlist lookup failed: %s", exc.code)
        return None
    return frozenset(i.appid for i in items or ())


async def fetch_store_recommendations(
    api: SteamWebApi,
    metadata: MetadataLookup,
    prices: PriceLookup,
    owned_cache: OwnedGamesCache,
    sessionmaker: Callable[[], async_sessionmaker[AsyncSession]],
    steam_id: str,
    *,
    cc: str,
    on_sale_only: bool,
    genre_threshold: float,
    max_price_batches: int,
) -> StoreRecommendationsResponse:
    owned = await load_owned_games(api, owned_cache, steam_id)
    owned_meta = await metadata.lookup((g.appid for g in owned), Priority.HIGH)
    coverage = compute_coverage((g.appid for g in owned), owned_meta)
    mode = choose_mode(coverage, genre_threshold)
    genres_by_appid = {a: s.genres for a, s in owned_meta.items() if s.status is FetchStatus.SUCCESS}
    preference = genre_preference(((g.appid, g.playtime_forever) for g in owned), genres_by_appid)

    async with sessionmaker()() as session:
        pool, pool_at = await candidate_pool(session, cc)
    if not pool:
        raise AppError(ErrorCode.DATA_NOT_READY, "아직 수집된 인기·할인 목록이 없습니다. 잠시 후 다시 시도해 주세요.", 503)

    owned_ids = frozenset(g.appid for g in owned)
    candidates = [a for a in pool if a not in owned_ids]
    cand_meta = await metadata.lookup(candidates, Priority.HIGH)
    cand_prices = await prices.lookup(candidates, max_batches=max_price_batches)
    wishlist = await wishlist_ids(api, steam_id)

    recommendations, count = recommend_store(
        pool,
        owned_ids,
        cand_meta,
        cand_prices,
        preference,
        mode=mode,
        on_sale_only=on_sale_only,
        wishlist=wishlist or frozenset(),
        coverage_ratio=coverage.ratio,
    )
    return StoreRecommendationsResponse(
        recommendations=recommendations,
        candidate_pool_size=len(candidates),
        candidate_count=count,
        metadata_pending=sum(1 for a in candidates if a not in cand_meta or cand_meta[a].status is FetchStatus.PENDING),
        price_pending=sum(1 for a in candidates if cand_prices[a].status is FetchStatus.PENDING),
        on_sale_only=on_sale_only,
        wishlist_checked=wishlist is not None,
        recommendation_mode=mode,
        metadata_coverage=coverage,
        pool_snapshot_at=pool_at,
        price_snapshot_at=latest_fetch(cand_prices.values()),
        calculated_at=datetime.now(UTC),
    )
