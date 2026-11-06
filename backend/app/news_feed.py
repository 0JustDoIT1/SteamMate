"""내 게임 소식(PRD v6.15): 최근 플레이한 보유 게임의 최신 공식 공지를 한 화면에 모은다.

- 대상: 최근 2주 플레이 시간 → 마지막 실행 시각 순으로 FEED_GAMES개(한 번도 실행 안 한 게임 제외).
- 게임마다 공지 FEED_PER_GAME개를 기존 뉴스 서비스로 받는다(발췌 캐시 10분을 함께 써 Steam 호출이 늘지 않게).
- 동시 요청 수를 묶고, 일부 게임이 실패해도 나머지를 보여 준다(실패 수는 응답에).
- 제목이 패치 공지 꼴이면 규모(대형/패치/핫픽스)를 붙인다(질문 기능의 제목 판정과 같은 규칙).
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Literal

from app.errors import AppError
from app.library import load_owned_games
from app.news import NewsService
from app.owned_cache import OwnedGamesCache
from app.qa.prompt import is_patch_title, update_scale
from app.schemas import CamelModel
from app.steam.web_api import SteamWebApi

logger = logging.getLogger(__name__)

FEED_GAMES = 10
FEED_PER_GAME = 3
FEED_ITEMS = 20
FEED_CONCURRENCY = 4


class FeedItem(CamelModel):
    appid: int
    game_name: str
    header_image: str | None
    gid: str
    title: str
    published_at: datetime
    url: str
    # 본문이 외부 사이트 링크뿐인 공지면 그 주소
    external_url: str | None
    # 패치 공지 꼴 제목이면 규모, 아니면 None(일반 공지)
    scale: Literal["MAJOR", "PATCH", "HOTFIX"] | None


class NewsFeedResponse(CamelModel):
    items: list[FeedItem]
    # 소식을 모은 게임 수와 그중 실패한 수
    game_count: int
    failed_count: int
    fetched_at: datetime


async def fetch_news_feed(
    api: SteamWebApi, owned_cache: OwnedGamesCache, news: NewsService, steam_id: str
) -> NewsFeedResponse:
    owned = await load_owned_games(api, owned_cache, steam_id)
    recent = sorted(
        (g for g in owned if g.rtime_last_played > 0),
        key=lambda g: (-(g.playtime_2weeks or 0), -g.rtime_last_played, g.appid),
    )[:FEED_GAMES]
    names = {g.appid: g.name or f"App {g.appid}" for g in recent}
    gate = asyncio.Semaphore(FEED_CONCURRENCY)

    async def one(appid: int) -> list[FeedItem] | None:
        async with gate:
            try:
                res = await news.get(appid, FEED_PER_GAME, None)
            except AppError as exc:
                logger.info("feed news skipped: appid=%s %s", appid, exc.code)
                return None
        return [
            FeedItem(
                appid=appid,
                game_name=res.name or names[appid],
                header_image=res.header_image,
                gid=item.gid,
                title=item.title,
                published_at=item.published_at,
                url=item.url,
                external_url=item.external_url,
                scale=update_scale(item.title) if is_patch_title(item.title) else None,  # type: ignore[arg-type]
            )
            for item in res.items
        ]

    results = await asyncio.gather(*(one(g.appid) for g in recent))
    items = [item for r in results if r for item in r]
    items.sort(key=lambda i: i.published_at, reverse=True)
    return NewsFeedResponse(
        items=items[:FEED_ITEMS],
        game_count=len(recent),
        failed_count=sum(r is None for r in results),
        fetched_at=datetime.now(UTC),
    )
