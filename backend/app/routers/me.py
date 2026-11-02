from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import current_steam_id, get_steam_api
from app.library import LibraryResponse, fetch_library
from app.steam.web_api import SteamWebApi

# 로그인한 본인 데이터만 다룬다. 경로·쿼리로 steamId를 받지 않는다.
router = APIRouter(prefix="/me", tags=["me"])


@router.get("/library", response_model=LibraryResponse)
async def my_library(
    steam_id: Annotated[str, Depends(current_steam_id)],
    api: Annotated[SteamWebApi, Depends(get_steam_api)],
) -> LibraryResponse:
    return await fetch_library(api, steam_id)
