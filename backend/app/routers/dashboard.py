from typing import Annotated

from fastapi import APIRouter, Depends

from app.dashboard import DashboardResponse, DashboardService, build_personal_context
from app.deps import (
    get_dashboard,
    get_metadata,
    get_owned_cache,
    get_steam_api,
    optional_steam_id,
)
from app.metadata.service import MetadataLookup
from app.owned_cache import OwnedGamesCache
from app.steam.web_api import SteamWebApi

router = APIRouter(prefix="/steam", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    service: Annotated[DashboardService, Depends(get_dashboard)],
    steam_id: Annotated[str | None, Depends(optional_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
    owned_cache: Annotated[OwnedGamesCache, Depends(get_owned_cache)],
    metadata: Annotated[MetadataLookup, Depends(get_metadata)],
) -> DashboardResponse:
    """공개 데이터라 로그인 없이 열람 가능. 로그인 상태면 세션 steamId로 보유·취향을 표시한다."""
    personal = await build_personal_context(api, owned_cache, metadata, steam_id) if steam_id else None
    return await service.build(personal)
