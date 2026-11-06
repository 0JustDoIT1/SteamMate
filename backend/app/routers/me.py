from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.achievements import AchievementsResponse, AchievementsService
from app.config import get_settings
from app.db import get_sessionmaker
from app.deals import DealsResponse, fetch_deals
from app.deps import (
    current_steam_id,
    get_achievements,
    get_metadata,
    get_news,
    get_owned_cache,
    get_prices,
    get_profile_cache,
    get_steam_api,
)
from app.library import LibraryResponse, fetch_library
from app.metadata.service import MetadataLookup
from app.news import NewsService
from app.news_feed import NewsFeedResponse, fetch_news_feed
from app.owned_cache import OwnedGamesCache
from app.prices import PriceLookup
from app.profile import ProfileCache, ProfileResponse
from app.recommend import RecommendationsResponse, fetch_recommendations
from app.steam.web_api import SteamWebApi
from app.store_recs import StoreRecommendationsResponse, fetch_store_recommendations

# 제외 목록은 브라우저에만 저장되고 요청마다 전달된다. 비정상적으로 긴 목록은 거부한다.
MAX_EXCLUDE = 1000

# 로그인한 본인 데이터만 다룬다. 경로·쿼리로 steamId를 받지 않는다.
router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile", response_model=ProfileResponse)
async def my_profile(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    profiles: Annotated[ProfileCache, Depends(get_profile_cache)],
) -> ProfileResponse:
    """위쪽 바의 닉네임·프로필 사진(공개 프로필 요약). 10분 메모리 캐시."""
    return await profiles.get(api, steam_id)


@router.get("/news-feed", response_model=NewsFeedResponse)
async def my_news_feed(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    owned_cache: Annotated[OwnedGamesCache, Depends(get_owned_cache)],
    news: Annotated[NewsService, Depends(get_news)],
) -> NewsFeedResponse:
    """최근 플레이한 보유 게임들의 최신 공식 공지(PRD v6.15)."""
    return await fetch_news_feed(api, owned_cache, news, steam_id)


@router.get("/achievements", response_model=AchievementsResponse)
async def my_achievements(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    owned_cache: Annotated[OwnedGamesCache, Depends(get_owned_cache)],
    metadata: Annotated[MetadataLookup, Depends(get_metadata)],
    achievements: Annotated[AchievementsService, Depends(get_achievements)],
) -> AchievementsResponse:
    """거의 다 깬 게임(업적 달성률 60~99%)과 완료한 게임 수(PRD v6.16). 메모리 6시간."""
    return await achievements.fetch(api, owned_cache, metadata, steam_id)


@router.get("/library", response_model=LibraryResponse)
async def my_library(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    metadata: Annotated[MetadataLookup, Depends(get_metadata)],
    owned_cache: Annotated[OwnedGamesCache, Depends(get_owned_cache)],
) -> LibraryResponse:
    return await fetch_library(api, metadata, owned_cache, steam_id)


@router.get("/recommendations", response_model=RecommendationsResponse)
async def my_recommendations(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    metadata: Annotated[MetadataLookup, Depends(get_metadata)],
    owned_cache: Annotated[OwnedGamesCache, Depends(get_owned_cache)],
    exclude: Annotated[list[Annotated[int, Field(gt=0)]], Query(max_length=MAX_EXCLUDE)] = [],  # noqa: B006
) -> RecommendationsResponse:
    return await fetch_recommendations(
        api,
        metadata,
        owned_cache,
        steam_id,
        exclude=frozenset(exclude),
        genre_threshold=get_settings().recommendation_genre_threshold,
    )


# 가격·상점 기준 국가는 서버 설정(store_cc) 하나만 지원한다(MVP: 한국 상점).


@router.get("/store-recommendations", response_model=StoreRecommendationsResponse)
async def my_store_recommendations(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    metadata: Annotated[MetadataLookup, Depends(get_metadata)],
    prices: Annotated[PriceLookup, Depends(get_prices)],
    owned_cache: Annotated[OwnedGamesCache, Depends(get_owned_cache)],
    on_sale_only: Annotated[bool, Query(alias="onSaleOnly")] = False,
) -> StoreRecommendationsResponse:
    settings = get_settings()
    return await fetch_store_recommendations(
        api,
        metadata,
        prices,
        owned_cache,
        get_sessionmaker,
        steam_id,
        cc=settings.store_cc,
        on_sale_only=on_sale_only,
        genre_threshold=settings.recommendation_genre_threshold,
        max_price_batches=settings.price_max_batches_per_request,
    )


@router.get("/deals", response_model=DealsResponse)
async def my_deals(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    metadata: Annotated[MetadataLookup, Depends(get_metadata)],
    prices: Annotated[PriceLookup, Depends(get_prices)],
    owned_cache: Annotated[OwnedGamesCache, Depends(get_owned_cache)],
) -> DealsResponse:
    return await fetch_deals(
        api,
        metadata,
        prices,
        owned_cache,
        steam_id,
        max_price_batches=get_settings().price_max_batches_per_request,
    )
