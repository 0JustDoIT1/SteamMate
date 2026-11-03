"""대시보드용 Steam 공개 집계 소스(모두 비문서화, 2026-11-03 응답 구조 확인).

각 소스는 ChartFetch로 정규화한다. 실패는 예외 대신 ChartFetch.failure로 돌려주고,
수집 작업이 FAILED 스냅샷으로 기록한다(이전 성공본은 계속 사용).
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.models import ChartSource

logger = logging.getLogger(__name__)

API = "https://api.steampowered.com"
FEATURED_URL = "https://store.steampowered.com/api/featuredcategories"
HEADER_IMAGE = "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
CHART_SIZE = 100


@dataclass(frozen=True)
class ChartItem:
    rank: int
    appid: int
    name: str | None = None
    last_week_rank: int | None = None
    metric_value: int | None = None
    final_price: int | None = None
    original_price: int | None = None
    discount_percent: int | None = None
    currency: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class ChartFetch:
    source: ChartSource
    items: list[ChartItem] = field(default_factory=list)
    period_start: datetime | None = None
    failure: str | None = None


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _TopSellerItem(_Loose):
    name: str | None = None


class _TopSellerRank(_Loose):
    rank: int
    appid: int
    last_week_rank: int | None = None
    consecutive_weeks: int | None = None
    item: _TopSellerItem | None = None


class _TopSellers(_Loose):
    start_date: int | None = None
    ranks: list[_TopSellerRank]


class _MostPlayedRank(_Loose):
    rank: int
    appid: int
    last_week_rank: int | None = None
    peak_in_game: int | None = None


class _MostPlayed(_Loose):
    rollup_date: int | None = None
    ranks: list[_MostPlayedRank]


class _ConcurrentRank(_Loose):
    rank: int
    appid: int
    concurrent_in_game: int | None = None


class _Concurrent(_Loose):
    ranks: list[_ConcurrentRank]


class _FeaturedItem(_Loose):
    id: int
    name: str | None = None
    type: int | None = None  # 0 = 게임(앱). 번들·패키지는 다른 값 [추정]
    discount_percent: int | None = None
    original_price: int | None = None
    final_price: int | None = None
    currency: str | None = None
    header_image: str | None = None


class _FeaturedCategory(_Loose):
    items: list[_FeaturedItem]


class _Featured(_Loose):
    specials: _FeaturedCategory
    new_releases: _FeaturedCategory


class ChartsApi:
    def __init__(self, http: httpx.AsyncClient, api_key: str, cc: str, language: str) -> None:
        self._http = http
        self._api_key = api_key
        self._cc = cc
        self._language = language

    async def top_sellers(self, start_date: datetime | None = None) -> ChartFetch:
        """전 세계 주간 판매 순위. start_date를 주면 그 주의 순위(과거 조회 가능, 52주 전까지 확인).

        최상위 country_code를 생략하면 전 세계 순위가 온다(context 국가가 달라도 같은 목록, 2026-11-03 확인).
        context의 country_code는 요청에 필요하지만 순위에는 영향을 주지 않는다.
        """
        payload: dict[str, Any] = {
            "context": {"language": self._language, "country_code": self._cc.upper()},
            "page_count": CHART_SIZE,
        }
        if start_date is not None:
            payload["start_date"] = int(start_date.timestamp())
        body = await self._get_json(
            ChartSource.TOP_SELLERS,
            f"{API}/IStoreTopSellersService/GetWeeklyTopSellers/v1/",
            {"input_json": json.dumps(payload)},
        )
        if isinstance(body, ChartFetch):
            return body
        data = _parse(ChartSource.TOP_SELLERS, _TopSellers, body.get("response"))
        if isinstance(data, ChartFetch):
            return data
        items = [
            ChartItem(
                rank=r.rank,
                appid=r.appid,
                name=r.item.name if r.item else None,
                last_week_rank=r.last_week_rank or None,
                metric_value=r.consecutive_weeks,
                image_url=HEADER_IMAGE.format(appid=r.appid),
            )
            for r in data.ranks
        ]
        return _result(ChartSource.TOP_SELLERS, items, data.start_date)

    async def most_played(self) -> ChartFetch:
        body = await self._get_json(ChartSource.MOST_PLAYED, f"{API}/ISteamChartsService/GetMostPlayedGames/v1/", {})
        if isinstance(body, ChartFetch):
            return body
        data = _parse(ChartSource.MOST_PLAYED, _MostPlayed, body.get("response"))
        if isinstance(data, ChartFetch):
            return data
        items = [
            ChartItem(
                rank=r.rank,
                appid=r.appid,
                last_week_rank=r.last_week_rank or None,
                metric_value=r.peak_in_game,
                image_url=HEADER_IMAGE.format(appid=r.appid),
            )
            for r in data.ranks
        ]
        return _result(ChartSource.MOST_PLAYED, items, data.rollup_date)

    async def concurrent(self) -> ChartFetch:
        body = await self._get_json(
            ChartSource.CONCURRENT,
            f"{API}/ISteamChartsService/GetGamesByConcurrentPlayers/v1/",
            {"key": self._api_key},
        )
        if isinstance(body, ChartFetch):
            return body
        data = _parse(ChartSource.CONCURRENT, _Concurrent, body.get("response"))
        if isinstance(data, ChartFetch):
            return data
        items = [
            ChartItem(
                rank=r.rank,
                appid=r.appid,
                metric_value=r.concurrent_in_game,
                image_url=HEADER_IMAGE.format(appid=r.appid),
            )
            for r in data.ranks
        ]
        return _result(ChartSource.CONCURRENT, items, None)

    async def featured(self) -> tuple[ChartFetch, ChartFetch]:
        """상점 기획 목록 1회 호출로 SPECIALS·NEW_RELEASES를 함께 만든다."""
        body = await self._get_json(ChartSource.SPECIALS, FEATURED_URL, {"cc": self._cc, "l": self._language})
        if isinstance(body, ChartFetch):
            return body, ChartFetch(ChartSource.NEW_RELEASES, failure=body.failure)
        data = _parse(ChartSource.SPECIALS, _Featured, body)
        if isinstance(data, ChartFetch):
            return data, ChartFetch(ChartSource.NEW_RELEASES, failure=data.failure)
        return (
            _result(ChartSource.SPECIALS, _featured_items(data.specials), None),
            _result(ChartSource.NEW_RELEASES, _featured_items(data.new_releases), None),
        )

    async def _get_json(self, source: ChartSource, url: str, params: dict[str, Any]) -> dict | ChartFetch:
        try:
            res = await self._http.get(url, params=params)
        except httpx.TimeoutException:
            return ChartFetch(source, failure="timeout")
        except httpx.HTTPError as exc:
            return ChartFetch(source, failure=f"network:{type(exc).__name__}")
        if res.status_code != 200:
            return ChartFetch(source, failure=f"http_{res.status_code}")
        try:
            body = res.json()
        except ValueError:
            return ChartFetch(source, failure="schema")
        return body if isinstance(body, dict) else ChartFetch(source, failure="schema")


def _parse(source: ChartSource, model: type[BaseModel], raw: Any) -> Any:
    try:
        return model.model_validate(raw)
    except ValidationError:
        logger.warning("chart source schema mismatch: %s", source)
        return ChartFetch(source, failure="schema")


def _featured_items(category: _FeaturedCategory) -> list[ChartItem]:
    seen: set[int] = set()
    items: list[ChartItem] = []
    for item in category.items:
        # 기획 목록에는 같은 게임이 중복되거나 번들이 섞일 수 있다.
        if item.id in seen or (item.type not in (None, 0)):
            continue
        seen.add(item.id)
        items.append(
            ChartItem(
                rank=len(items) + 1,
                appid=item.id,
                name=item.name,
                final_price=item.final_price,
                original_price=item.original_price,
                discount_percent=item.discount_percent,
                currency=item.currency,
                image_url=item.header_image or HEADER_IMAGE.format(appid=item.id),
            )
        )
    return items


def _result(source: ChartSource, items: list[ChartItem], period_ts: int | None) -> ChartFetch:
    if not items:
        # 빈 목록은 정상이라 보기 어렵다(구조 변경 등). 이전 성공본을 유지하도록 실패로 기록한다.
        return ChartFetch(source, failure="empty")
    period = datetime.fromtimestamp(period_ts, UTC) if period_ts else None
    return ChartFetch(source, items=items, period_start=period)
