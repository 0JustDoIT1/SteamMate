"""라우터 공용 의존성. 외부 HTTP 클라이언트·세션은 app.state에서 꺼내 테스트에서 교체할 수 있게 한다."""

import httpx
from fastapi import Request

from app.auth.session import COOKIE_NAME, SessionManager
from app.auth.steam_openid import NonceStore
from app.config import get_settings
from app.dashboard import DashboardService
from app.errors import AppError, ErrorCode
from app.metadata.service import MetadataLookup
from app.owned_cache import OwnedGamesCache
from app.steam.web_api import SteamWebApi


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def get_sessions(request: Request) -> SessionManager:
    return request.app.state.sessions


def get_nonces(request: Request) -> NonceStore:
    return request.app.state.nonces


def get_metadata(request: Request) -> MetadataLookup:
    return request.app.state.metadata


def get_owned_cache(request: Request) -> OwnedGamesCache:
    return request.app.state.owned


def get_dashboard(request: Request) -> DashboardService:
    return request.app.state.dashboard


def get_steam_api(request: Request) -> SteamWebApi:
    return SteamWebApi(get_http(request), get_settings().steam_api_key)


def optional_steam_id(request: Request) -> str | None:
    return get_sessions(request).read(request.cookies.get(COOKIE_NAME))


def current_steam_id(request: Request) -> str:
    """로그인 필수 API용. 세션의 steamId만 신뢰한다(클라이언트 입력 steamId는 받지 않음)."""
    steam_id = optional_steam_id(request)
    if steam_id is None:
        raise AppError(ErrorCode.UNAUTHENTICATED, "Steam 로그인이 필요합니다.", 401)
    return steam_id
