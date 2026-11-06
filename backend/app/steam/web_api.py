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
    # 공개 프로필 표시용(위쪽 바). 비공개 프로필도 닉네임·사진은 준다
    personaname: str = ""
    avatarmedium: str | None = None
    profileurl: str | None = None


class AchievementsPrivate(Exception):
    """사용자의 Steam 업적(게임 세부 정보)이 비공개."""


class SchemaAchievement(_Loose):
    name: str = ""
    displayName: str = ""


class SchemaStats(_Loose):
    achievements: list[SchemaAchievement] = []


class SchemaGame(_Loose):
    availableGameStats: SchemaStats | None = None


class SchemaResponse(_Loose):
    game: SchemaGame | None = None


class PlayerSummariesBody(_Loose):
    players: list[PlayerSummary]


class PlayerSummariesResponse(_Loose):
    response: PlayerSummariesBody


class WishlistItem(_Loose):
    appid: int
    priority: int = 0
    date_added: int = 0


class WishlistBody(_Loose):
    # 비공개 위시리스트는 HTTP 200 + 빈 객체({})로 온다(2026-11-03 확인).
    # 공개인데 비어 있어도 같은 모양일 가능성이 높다(protobuf 기본값 생략, 미확인) → 구분하지 않는다.
    items: list[WishlistItem] | None = None


class WishlistResponse(_Loose):
    response: WishlistBody


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

    async def get_wishlist(self, steam_id: str) -> list[WishlistItem] | None:
        """본인 공개 위시리스트. 비어 있거나 비공개면 None.

        API 키 없이 호출한다: 키를 붙이면 키 소유 계정은 비공개여도 조회될 수 있어 공개 범위를 존중하지 못한다.
        """
        data = await self._get(
            "/IWishlistService/GetWishlist/v1/", {"steamid": steam_id}, WishlistResponse, with_key=False
        )
        return data.response.items or None

    async def get_player_achievements(self, steam_id: str, appid: int) -> list[tuple[str, bool]] | None:
        """(업적 이름, 달성 여부) 목록. 업적이 없는 게임이면 None, 업적이 비공개면 AchievementsPrivate.

        Steam은 비공개를 HTTP 403(+ "Profile is not public")으로 알려 공용 _get의 "API 키 거부" 처리와 겹친다 →
        상태 코드와 본문을 직접 본다(PRD v6.16).
        """
        path = "/ISteamUserStats/GetPlayerAchievements/v1/"
        try:
            res = await self._http.get(f"{BASE_URL}{path}", params={"key": self._api_key, "steamid": steam_id, "appid": appid})
        except httpx.TimeoutException as exc:
            raise AppError(ErrorCode.STEAM_TIMEOUT, "Steam 응답이 지연되고 있습니다.", 504) from exc
        except httpx.HTTPError as exc:
            logger.warning("steam request failed: %s %s", path, type(exc).__name__)
            raise _unavailable() from exc
        try:
            stats = res.json().get("playerstats") or {}
        except ValueError:
            stats = {}
        error = str(stats.get("error") or "").lower()
        if res.status_code == 403 and "not public" in error:
            raise AchievementsPrivate()
        if res.status_code == 400 and "no stats" in error:
            return None
        if res.status_code == 429:
            raise AppError(
                ErrorCode.STEAM_RATE_LIMITED, "Steam 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.", 503
            )
        if res.status_code != 200:
            logger.warning("steam unexpected status: %s HTTP %s", path, res.status_code)
            raise _unavailable()
        items = stats.get("achievements")
        if not isinstance(items, list):
            return None
        return [(str(a.get("apiname", "")), bool(a.get("achieved"))) for a in items if isinstance(a, dict)]

    async def get_achievement_names(self, appid: int, language: str = "koreana") -> dict[str, str]:
        """업적 이름(apiname) → 표시 이름(가능하면 한국어). 없으면 빈 사전."""
        data = await self._get("/ISteamUserStats/GetSchemaForGame/v2/", {"appid": appid, "l": language}, SchemaResponse)
        game = data.game
        achievements = game.availableGameStats.achievements if game and game.availableGameStats else []
        return {a.name: a.displayName for a in achievements if a.name and a.displayName}

    async def _get(self, path: str, params: dict[str, Any], model: type[T], with_key: bool = True) -> T:
        try:
            res = await self._http.get(
                f"{BASE_URL}{path}", params={**params, "key": self._api_key} if with_key else params
            )
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
