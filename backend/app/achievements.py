"""거의 다 깬 게임(PRD v6.16): 보유 게임의 Steam 업적 달성률로 "조금만 더 하면 완료"인 게임을 고른다.

- 대상: 2시간 이상 플레이한 게임 중 플레이 시간 상위 CANDIDATES개(게임마다 업적 API 한 번).
- 결과: 달성률 MIN_RATE 이상 100% 미만을 달성률 순 SHOWN개 + 남은 업적 이름(한국어, 최대 REMAINING_SHOWN개).
  업적이 없는 게임·0%·오류는 건너뛴다. 0%이면서 오래 한 게임은 업적을 Steam 밖에서 관리하는 경우가 있다(R6 Siege).
- 저장하지 않는다(개인 데이터). 사용자·게임별 업적과 게임별 업적 이름을 메모리에 CACHE_SECONDS 동안 둔다.
- 업적이 비공개면(Steam 403 "Profile is not public") status=PRIVATE로 알린다.
"""

import asyncio
import logging
from datetime import UTC, datetime
from enum import StrEnum

from cachetools import TTLCache

from app.errors import AppError
from app.library import load_owned_games
from app.metadata.service import MetadataLookup, Priority
from app.owned_cache import OwnedGamesCache
from app.schemas import CamelModel
from app.steam.web_api import AchievementsPrivate, SteamWebApi

logger = logging.getLogger(__name__)

MIN_PLAYTIME_MINUTES = 120
CANDIDATES = 30
MIN_RATE = 0.6
SHOWN = 5
REMAINING_SHOWN = 3
CONCURRENCY = 4
CACHE_SECONDS = 6 * 3600


class AchievementStatus(StrEnum):
    OK = "OK"
    PRIVATE = "PRIVATE"  # Steam 업적(게임 세부 정보)이 비공개


class NearlyDoneGame(CamelModel):
    appid: int
    name: str
    header_image: str | None
    achieved: int
    total: int
    # 아직 달성하지 않은 업적 표시 이름(최대 REMAINING_SHOWN개). 이름을 못 받으면 비어 있다
    remaining: list[str]


class AchievementsResponse(CamelModel):
    status: AchievementStatus
    nearly_done: list[NearlyDoneGame]
    # 업적을 모두 달성한 게임 수(확인한 게임 중)
    completed_count: int
    # 업적 API로 확인한 게임 수(업적 없는 게임·오류 제외)
    checked_count: int
    fetched_at: datetime


_Progress = list[tuple[str, bool]] | None


class AchievementsService:
    def __init__(self, cache_seconds: float = CACHE_SECONDS) -> None:
        self._progress: TTLCache[tuple[str, int], _Progress] = TTLCache(maxsize=20_000, ttl=cache_seconds)
        self._names: TTLCache[int, dict[str, str]] = TTLCache(maxsize=2_000, ttl=cache_seconds)

    async def fetch(
        self, api: SteamWebApi, owned_cache: OwnedGamesCache, metadata: MetadataLookup, steam_id: str
    ) -> AchievementsResponse:
        owned = await load_owned_games(api, owned_cache, steam_id)
        candidates = sorted(
            (g for g in owned if g.playtime_forever >= MIN_PLAYTIME_MINUTES),
            key=lambda g: (-g.playtime_forever, g.appid),
        )[:CANDIDATES]
        gate = asyncio.Semaphore(CONCURRENCY)
        private = False

        async def progress(appid: int) -> _Progress:
            nonlocal private
            key = (steam_id, appid)
            if key in self._progress:
                return self._progress[key]
            async with gate:
                try:
                    result = await api.get_player_achievements(steam_id, appid)
                except AchievementsPrivate:
                    private = True
                    return None
                except AppError as exc:  # 한 게임 실패는 건너뛴다(캐시하지 않아 다음에 다시 시도)
                    logger.info("achievements skipped: appid=%s %s", appid, exc.code)
                    return None
            self._progress[key] = result
            return result

        results = await asyncio.gather(*(progress(g.appid) for g in candidates))
        if private:
            return AchievementsResponse(status=AchievementStatus.PRIVATE, nearly_done=[], completed_count=0,
                                        checked_count=0, fetched_at=datetime.now(UTC))

        rated = []
        completed = checked = 0
        for game, items in zip(candidates, results, strict=True):
            if not items:
                continue
            checked += 1
            done = sum(achieved for _, achieved in items)
            if done == len(items):
                completed += 1
            elif done / len(items) >= MIN_RATE:
                rated.append((game, items, done))
        rated.sort(key=lambda r: (-(r[2] / len(r[1])), len(r[1]) - r[2], r[0].appid))
        top = rated[:SHOWN]

        meta = await metadata.lookup([g.appid for g, _, _ in top], Priority.HIGH)
        names = await asyncio.gather(*(self._achievement_names(api, g.appid) for g, _, _ in top))
        nearly_done = [
            NearlyDoneGame(
                appid=game.appid,
                name=game.name or f"App {game.appid}",
                header_image=meta[game.appid].header_image if game.appid in meta else None,
                achieved=done,
                total=len(items),
                remaining=[label for apiname, ok in items if not ok and (label := shown.get(apiname))][:REMAINING_SHOWN],
            )
            for (game, items, done), shown in zip(top, names, strict=True)
        ]
        return AchievementsResponse(status=AchievementStatus.OK, nearly_done=nearly_done, completed_count=completed,
                                    checked_count=checked, fetched_at=datetime.now(UTC))

    async def _achievement_names(self, api: SteamWebApi, appid: int) -> dict[str, str]:
        if appid in self._names:
            return self._names[appid]
        try:
            names = await api.get_achievement_names(appid)
        except AppError as exc:  # 이름이 없어도 진행률은 보인다
            logger.info("achievement names skipped: appid=%s %s", appid, exc.code)
            return {}
        self._names[appid] = names
        return names
