"""로그인한 사용자 본인의 Steam 라이브러리 조회. 결과는 저장하지 않는다(PRD 개인 데이터 비저장)."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.errors import AppError, ErrorCode
from app.steam.web_api import PUBLIC_VISIBILITY, OwnedGame, SteamWebApi

ICON_URL = "https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{hash}.jpg"
PRIVACY_SETTINGS_URL = "https://steamcommunity.com/my/edit/settings"


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LibraryGame(CamelModel):
    appid: int
    name: str
    playtime_forever: int
    playtime_2weeks: int
    last_played_at: datetime | None
    icon_url: str | None


class LibrarySummary(CamelModel):
    total_playtime_minutes: int
    played_count: int
    unplayed_count: int
    recently_played_count: int


class LibraryResponse(CamelModel):
    steam_id: str
    game_count: int
    games: list[LibraryGame]
    summary: LibrarySummary
    fetched_at: datetime


async def fetch_library(api: SteamWebApi, steam_id: str) -> LibraryResponse:
    body = await api.get_owned_games(steam_id)
    if body.games is None and body.game_count is None:
        await _raise_private_reason(api, steam_id)

    games = sorted(
        (_to_library_game(g) for g in body.games or []),
        key=lambda g: (-g.playtime_forever, g.appid),
    )
    return LibraryResponse(
        steam_id=steam_id,
        game_count=len(games),
        games=games,
        summary=summarize(games),
        fetched_at=datetime.now(UTC),
    )


async def _raise_private_reason(api: SteamWebApi, steam_id: str) -> None:
    player = await api.get_player_summary(steam_id)
    if player is None:
        raise AppError(ErrorCode.PROFILE_NOT_FOUND, "Steam 계정을 찾을 수 없습니다.", 404)
    if player.communityvisibilitystate != PUBLIC_VISIBILITY:
        message = "Steam 프로필이 비공개입니다. 프로필과 게임 세부 정보를 '공개'로 바꿔 주세요."
    else:
        message = "Steam 게임 세부 정보가 비공개입니다. 공개 설정에서 '게임 세부 정보'를 '공개'로 바꿔 주세요."
    raise AppError(ErrorCode.LIBRARY_PRIVATE, f"{message} ({PRIVACY_SETTINGS_URL})", 403)


def _to_library_game(game: OwnedGame) -> LibraryGame:
    return LibraryGame(
        appid=game.appid,
        name=game.name or f"App {game.appid}",
        playtime_forever=game.playtime_forever,
        playtime_2weeks=game.playtime_2weeks or 0,
        last_played_at=datetime.fromtimestamp(game.rtime_last_played, UTC) if game.rtime_last_played else None,
        icon_url=ICON_URL.format(appid=game.appid, hash=game.img_icon_url) if game.img_icon_url else None,
    )


def summarize(games: list[LibraryGame]) -> LibrarySummary:
    played = sum(1 for g in games if g.playtime_forever > 0)
    return LibrarySummary(
        total_playtime_minutes=sum(g.playtime_forever for g in games),
        played_count=played,
        unplayed_count=len(games) - played,
        recently_played_count=sum(1 for g in games if g.playtime_2weeks > 0),
    )
