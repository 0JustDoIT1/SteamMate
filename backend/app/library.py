"""로그인한 사용자 본인의 Steam 라이브러리 조회. 결과는 저장하지 않는다(PRD 개인 데이터 비저장).

게임 장르는 공용 메타데이터 캐시에서 붙인다. 캐시에 없는 게임은 백그라운드로 보강되고 응답은 기다리지 않는다.
"""

from datetime import UTC, datetime

from app.errors import AppError, ErrorCode
from app.genre_labels import korean_genres
from app.metadata.coverage import MetadataCoverage, compute_coverage, snapshot_at
from app.metadata.service import MetadataLookup, MetadataSnapshot, Priority
from app.models import FetchStatus
from app.owned_cache import OwnedGamesCache
from app.schemas import CamelModel
from app.steam.web_api import PUBLIC_VISIBILITY, OwnedGame, SteamWebApi

ICON_URL = "https://media.steampowered.com/steamcommunity/public/images/apps/{appid}/{hash}.jpg"
PRIVACY_SETTINGS_URL = "https://steamcommunity.com/my/edit/settings"


class LibraryGame(CamelModel):
    appid: int
    name: str
    playtime_forever: int
    playtime_2weeks: int
    last_played_at: datetime | None
    icon_url: str | None
    metadata_status: FetchStatus
    app_type: str | None
    genres: list[str]


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
    metadata_coverage: MetadataCoverage
    metadata_snapshot_at: datetime | None
    fetched_at: datetime


async def fetch_library(
    api: SteamWebApi, metadata: MetadataLookup, owned_cache: OwnedGamesCache, steam_id: str
) -> LibraryResponse:
    body = await owned_cache.get(api, steam_id)
    if body.games is None and body.game_count is None:
        await _raise_private_reason(api, steam_id)

    owned = body.games or []
    snapshots = await metadata.lookup((g.appid for g in owned), Priority.HIGH)
    games = sorted(
        (_to_library_game(g, snapshots.get(g.appid)) for g in owned),
        key=lambda g: (-g.playtime_forever, g.appid),
    )
    return LibraryResponse(
        steam_id=steam_id,
        game_count=len(games),
        games=games,
        summary=summarize(games),
        metadata_coverage=compute_coverage((g.appid for g in owned), snapshots),
        metadata_snapshot_at=snapshot_at(snapshots.values()),
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


def _to_library_game(game: OwnedGame, meta: MetadataSnapshot | None) -> LibraryGame:
    return LibraryGame(
        appid=game.appid,
        name=game.name or f"App {game.appid}",
        playtime_forever=game.playtime_forever,
        playtime_2weeks=game.playtime_2weeks or 0,
        last_played_at=datetime.fromtimestamp(game.rtime_last_played, UTC) if game.rtime_last_played else None,
        icon_url=ICON_URL.format(appid=game.appid, hash=game.img_icon_url) if game.img_icon_url else None,
        metadata_status=meta.status if meta else FetchStatus.PENDING,
        app_type=meta.app_type if meta else None,
        genres=korean_genres(meta.genres) if meta and meta.status is FetchStatus.SUCCESS else [],
    )


def summarize(games: list[LibraryGame]) -> LibrarySummary:
    played = sum(1 for g in games if g.playtime_forever > 0)
    return LibrarySummary(
        total_playtime_minutes=sum(g.playtime_forever for g in games),
        played_count=played,
        unplayed_count=len(games) - played,
        recently_played_count=sum(1 for g in games if g.playtime_2weeks > 0),
    )
