"""Steam Web API(api.steampowered.com) 클라이언트. 응답은 Pydantic으로 검증한다."""

import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

BASE_URL = "https://api.steampowered.com"
PUBLIC_VISIBILITY = 3  # communityvisibilitystate: 3 = 공개

T = TypeVar("T", bound=BaseModel)


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class OwnedGame(_Loose):
    appid: int
    name: str = ""
    playtime_forever: int = 0
    playtime_2weeks: int | None = None
    rtime_last_played: int = 0
    img_icon_url: str = ""


class OwnedGamesBody(_Loose):
    # 비공개 라이브러리는 HTTP 200 + 빈 객체({})로 응답한다.
    game_count: int | None = None
    games: list[OwnedGame] | None = None


class OwnedGamesResponse(_Loose):
    response: OwnedGamesBody


class PlayerSummary(_Loose):
    steamid: str
    communityvisibilitystate: int


class PlayerSummariesBody(_Loose):
    players: list[PlayerSummary]


class PlayerSummariesResponse(_Loose):
    response: PlayerSummariesBody


class SteamWebApi:
    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def get_owned_games(self, steam_id: str) -> OwnedGamesBody:
        data = await self._get(
            "/IPlayerService/GetOwnedGames/v1/",
            {"steamid": steam_id, "include_appinfo": 1, "include_played_free_games": 1},
            OwnedGamesResponse,
        )
        return data.response

    async def get_player_summary(self, steam_id: str) -> PlayerSummary | None:
        data = await self._get(
            "/ISteamUser/GetPlayerSummaries/v2/", {"steamids": steam_id}, PlayerSummariesResponse
        )
        return next((p for p in data.response.players if p.steamid == steam_id), None)

    async def _get(self, path: str, params: dict[str, Any], model: type[T]) -> T:
        try:
            res = await self._http.get(f"{BASE_URL}{path}", params={**params, "key": self._api_key})
        except httpx.TimeoutException as exc:
            raise AppError(ErrorCode.STEAM_TIMEOUT, "Steam 응답이 지연되고 있습니다.", 504) from exc
        except httpx.HTTPError as exc:
            logger.warning("steam request failed: %s %s", path, type(exc).__name__)
            raise _unavailable() from exc

        if res.status_code == 429:
            raise AppError(
                ErrorCode.STEAM_RATE_LIMITED, "Steam 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.", 503
            )
        if res.status_code in (401, 403):
            # 서버 설정 문제(API 키). 사용자에게는 일반 오류로 보인다.
            logger.error("steam api key rejected: %s HTTP %s", path, res.status_code)
            raise _unavailable()
        if res.status_code != 200:
            logger.warning("steam unexpected status: %s HTTP %s", path, res.status_code)
            raise _unavailable()

        try:
            return model.model_validate(res.json())
        except (ValueError, ValidationError) as exc:
            logger.warning("steam response schema mismatch: %s", path)
            raise _unavailable() from exc


def _unavailable() -> AppError:
    return AppError(ErrorCode.STEAM_UNAVAILABLE, "Steam 서비스에 일시적인 문제가 있습니다.", 502)
