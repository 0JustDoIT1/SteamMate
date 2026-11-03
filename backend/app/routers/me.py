from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.config import get_settings
from app.deps import current_steam_id, get_metadata, get_owned_cache, get_steam_api
from app.library import LibraryResponse, fetch_library
from app.metadata.service import MetadataLookup
from app.owned_cache import OwnedGamesCache
from app.recommend import RecommendationsResponse, fetch_recommendations
from app.steam.web_api import SteamWebApi

# 제외 목록은 브라우저에만 저장되고 요청마다 전달된다. 비정상적으로 긴 목록은 거부한다.
MAX_EXCLUDE = 1000

# 로그인한 본인 데이터만 다룬다. 경로·쿼리로 steamId를 받지 않는다.
router = APIRouter(prefix="/me", tags=["me"])


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
    prefer_unplayed: Annotated[bool, Query(alias="preferUnplayed")] = False,
    exclude: Annotated[list[Annotated[int, Field(gt=0)]], Query(max_length=MAX_EXCLUDE)] = [],  # noqa: B006
) -> RecommendationsResponse:
    return await fetch_recommendations(
        api,
        metadata,
        owned_cache,
        steam_id,
        prefer_unplayed=prefer_unplayed,
        exclude=frozenset(exclude),
        genre_threshold=get_settings().recommendation_genre_threshold,
    )
