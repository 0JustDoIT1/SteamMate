"""게임 공식 뉴스 목록(F6 R1: 목록·발췌·원문 링크). 공개 데이터라 로그인 없이 볼 수 있다.

- Steam GetNewsForApp에서 공식 공지(steam_community_announcements)만 받는다. 키 불필요.
- `maxlength`는 쓰지 않는다: 쓰면 Steam이 서식을 지우며 문단을 붙여 버린다(2026-11-03 확인). 전문을 받아 정리한다.
- 응답·캐시에는 정리한 앞부분 발췌만 둔다. 본문 전문은 저장·캐시·로그하지 않는다(PRD: 권리 미확인 본문 비보관).
  예외: AI 질문(app.qa)은 fetch_full로 전문을 받아 요청 처리 중·짧은 메모리 캐시에서만 쓴다(PRD F6 4번).
- 원문 링크는 appid와 gid로 만든 상점 공지 주소(API의 url 필드는 중간 주소라 쓰지 않는다).
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from cachetools import TTLCache
from pydantic import BaseModel, ConfigDict, ValidationError

from app.errors import AppError, ErrorCode
from app.metadata.service import MetadataLookup, Priority
from app.news_cleaner import clean_news, excerpt, link_only_target
from app.schemas import CamelModel

logger = logging.getLogger(__name__)

NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
OFFICIAL_FEED = "steam_community_announcements"
STORE_NEWS_URL = "https://store.steampowered.com/news/app/{appid}/view/{gid}"
EXCERPT_CHARS = 200


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _RawItem(_Loose):
    gid: str
    title: str
    author: str = ""
    contents: str = ""
    date: int


class _AppNews(_Loose):
    newsitems: list[_RawItem] = []


class _NewsBody(_Loose):
    appnews: _AppNews


class NewsItem(CamelModel):
    gid: str
    title: str
    author: str | None
    published_at: datetime
    excerpt: str
    url: str
    # 본문이 외부 사이트 링크뿐인 공지("전문은 여기서")면 그 주소. 이때 excerpt는 비운다.
    external_url: str | None


@dataclass(frozen=True)
class FullNews:
    gid: str
    title: str
    published_at: datetime
    url: str
    text: str  # clean_news 결과 전문


class NewsResponse(CamelModel):
    appid: int
    # 게임 이름·대표 이미지(메타데이터 캐시에 있을 때만)
    name: str | None
    header_image: str | None
    items: list[NewsItem]
    # 더 오래된 글을 받을 때 넘길 값(before). 더 없으면 None
    next_before: int | None
    fetched_at: datetime
    # 이 환경에서 AI 질문(POST /steam/news/ask)을 쓸 수 있는지(기능 플래그)
    ask_enabled: bool = False


class NewsService:
    def __init__(self, http: httpx.AsyncClient, metadata: MetadataLookup, cache_seconds: float) -> None:
        self._http = http
        self._metadata = metadata
        # (appid, count, before) → (발췌 목록, 다음 before, 받은 시각). 발췌만 담는다.
        self._cache: TTLCache[tuple[int, int, int | None], tuple[list[NewsItem], int | None, datetime]] = TTLCache(
            maxsize=512, ttl=cache_seconds
        )

    async def get(self, appid: int, count: int, before: int | None) -> NewsResponse:
        key = (appid, count, before)
        cached = self._cache.get(key)
        if cached is None:
            cached = await self._fetch(appid, count, before)
            self._cache[key] = cached
        items, next_before, fetched_at = cached
        meta = (await self._metadata.lookup([appid], Priority.HIGH)).get(appid)
        return NewsResponse(
            appid=appid,
            name=meta.name if meta else None,
            header_image=meta.header_image if meta else None,
            items=items,
            next_before=next_before,
            fetched_at=fetched_at,
        )

    async def _fetch(self, appid: int, count: int, before: int | None) -> tuple[list[NewsItem], int | None, datetime]:
        # 하나 더 받아 다음 페이지가 있는지 안다.
        raw = await self._request(appid, count + 1, before)
        page, extra = raw[:count], raw[count:]
        items = [item for r in page if (item := _to_item(appid, r)) is not None]
        # 같은 시각의 글이 페이지 경계에 걸리면 겹칠 수 있어 1초 앞에서 다음 페이지를 시작한다.
        next_before = page[-1].date - 1 if extra and page else None
        return items, next_before, datetime.now(UTC)

    async def fetch_full(self, appid: int, count: int, before: int | None) -> list[FullNews]:
        """AI 질문용 공식 공지 전문(정리 후). 캐시하지 않는다 — 보관 여부는 호출자가 TTL로 정한다.

        외부 링크뿐인 공지와 정리 후 본문이 빈 글은 근거로 쓸 수 없어 뺀다.
        """
        out = []
        for r in await self._request(appid, count, before):
            if not re.fullmatch(r"\d{1,20}", r.gid) or link_only_target(r.contents):
                continue
            text = clean_news(r.contents)
            if text:
                out.append(FullNews(
                    gid=r.gid,
                    title=r.title.strip() or "(제목 없음)",
                    published_at=datetime.fromtimestamp(r.date, UTC),
                    url=STORE_NEWS_URL.format(appid=appid, gid=r.gid),
                    text=text,
                ))
        return out

    async def _request(self, appid: int, count: int, before: int | None) -> list[_RawItem]:
        params: dict[str, int | str] = {"appid": appid, "count": count, "feeds": OFFICIAL_FEED}
        if before is not None:
            params["enddate"] = before
        try:
            res = await self._http.get(NEWS_URL, params=params)
        except httpx.TimeoutException as exc:
            raise AppError(ErrorCode.STEAM_TIMEOUT, "Steam 응답이 지연되고 있습니다.", 504) from exc
        except httpx.HTTPError as exc:
            logger.warning("news request failed: appid=%s %s", appid, type(exc).__name__)
            raise _unavailable() from exc

        if res.status_code == 403:
            # 없는 appid는 403 + 빈 객체(2026-11-03 확인)
            raise AppError(ErrorCode.NOT_FOUND, "Steam에서 이 게임의 뉴스를 찾을 수 없습니다.", 404)
        if res.status_code == 429:
            raise AppError(ErrorCode.STEAM_RATE_LIMITED, "Steam 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.", 503)
        if res.status_code != 200:
            logger.warning("news unexpected status: appid=%s HTTP %s", appid, res.status_code)
            raise _unavailable()
        try:
            return _NewsBody.model_validate(res.json()).appnews.newsitems
        except (ValueError, ValidationError) as exc:
            logger.warning("news schema mismatch: appid=%s", appid)
            raise _unavailable() from exc


def _to_item(appid: int, raw: _RawItem) -> NewsItem | None:
    if not re.fullmatch(r"\d{1,20}", raw.gid):
        logger.warning("news item with unexpected gid skipped: appid=%s", appid)
        return None
    external = link_only_target(raw.contents)
    return NewsItem(
        gid=raw.gid,
        title=raw.title.strip() or "(제목 없음)",
        author=raw.author.strip() or None,
        published_at=datetime.fromtimestamp(raw.date, UTC),
        excerpt="" if external else excerpt(clean_news(raw.contents), EXCERPT_CHARS),
        url=STORE_NEWS_URL.format(appid=appid, gid=raw.gid),
        external_url=external,
    )


def _unavailable() -> AppError:
    return AppError(ErrorCode.STEAM_UNAVAILABLE, "Steam 서비스에 일시적인 문제가 있습니다.", 502)
