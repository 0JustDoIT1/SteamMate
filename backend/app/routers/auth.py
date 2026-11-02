from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.auth.session import COOKIE_NAME, SessionManager
from app.auth.steam_openid import NonceStore, build_login_url, verify_callback
from app.config import get_settings
from app.deps import current_steam_id, get_http, get_nonces, get_sessions
from app.errors import AppError

router = APIRouter(prefix="/auth", tags=["auth"])

# 브라우저는 Next /api 프록시를 거쳐 콜백으로 돌아온다.
CALLBACK_PATH = "/api/auth/steam/callback"


class MeResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    steam_id: str


def _return_to() -> str:
    return get_settings().public_base_url.rstrip("/") + CALLBACK_PATH


@router.get("/steam/login")
async def steam_login() -> RedirectResponse:
    realm = get_settings().public_base_url.rstrip("/")
    return RedirectResponse(build_login_url(_return_to(), realm), status_code=302)


@router.get("/steam/callback")
async def steam_callback(
    request: Request,
    http: Annotated[httpx.AsyncClient, Depends(get_http)],
    sessions: Annotated[SessionManager, Depends(get_sessions)],
    nonces: Annotated[NonceStore, Depends(get_nonces)],
) -> RedirectResponse:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    try:
        steam_id = await verify_callback(dict(request.query_params), _return_to(), http, nonces)
    except AppError as exc:
        # 브라우저 이동 요청이므로 JSON 대신 첫 화면으로 돌려보내고 실패를 표시한다.
        return RedirectResponse(f"{base}/?{urlencode({'login': 'failed', 'code': exc.code})}", status_code=302)

    response = RedirectResponse(f"{base}/me", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        sessions.issue(steam_id),
        max_age=sessions.max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return response


@router.get("/me", response_model=MeResponse)
async def me(steam_id: Annotated[str, Depends(current_steam_id)]) -> MeResponse:
    return MeResponse(steam_id=steam_id)


@router.post("/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
