"""게임 가격 캐시(game_price). 상점 가격을 (appid, cc)별로 짧게(기본 1시간) 저장한다.

가격은 여러 게임을 한 요청으로 받을 수 있어(최대 100개씩 나눔) 메타데이터처럼 백그라운드 대기열을 두지 않는다.
lookup()이 만료·누락된 게임을 그 자리에서 받되 `max_batches`로 한 번에 받는 묶음 수를 제한한다.
제한을 넘은 나머지는 PENDING으로 돌려주고, 화면 폴링이 다음 요청에서 이어 받는다.
상점 요청은 메타데이터 수집과 같은 레이트리미터를 쓴다(같은 상점 서버).
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.rate_limit import TokenBucket
from app.models import FetchStatus, GamePrice
from app.schemas import CamelModel
from app.steam.store_api import Outcome, PriceResult, StoreApi

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


@dataclass(frozen=True)
class PricePolicy:
    ttl: timedelta
    retry_error: timedelta
    retry_rate_limited: timedelta
    retry_not_found: timedelta


@dataclass(frozen=True)
class PriceSnapshot:
    appid: int
    status: FetchStatus
    currency: str | None = None
    initial_price: int | None = None
    final_price: int | None = None
    discount_percent: int | None = None
    fetched_at: datetime | None = None
    # 다시 조회할 시각(성공·없음은 만료, 일시 실패는 재시도). None이면 바로 조회 대상.
    due_at: datetime | None = None

    @property
    def has_price(self) -> bool:
        return self.status is FetchStatus.SUCCESS and self.final_price is not None

    @property
    def on_sale(self) -> bool:
        return self.has_price and (self.discount_percent or 0) > 0


class PriceInfo(CamelModel):
    """응답용 가격. 금액은 Steam 최소 단위×100."""

    currency: str
    initial_price: int
    final_price: int
    discount_percent: int


def price_info(snap: PriceSnapshot | None) -> PriceInfo | None:
    if snap is None or not snap.has_price or snap.currency is None:
        return None
    return PriceInfo(
        currency=snap.currency,
        initial_price=snap.initial_price if snap.initial_price is not None else snap.final_price,
        final_price=snap.final_price,
        discount_percent=snap.discount_percent or 0,
    )


def latest_fetch(snaps: Iterable[PriceSnapshot]) -> datetime | None:
    """응답에 쓰인 가격의 기준 시각 = SUCCESS 행의 max(fetched_at)."""
    return max((s.fetched_at for s in snaps if s.status is FetchStatus.SUCCESS and s.fetched_at), default=None)


class PriceLookup(Protocol):
    async def lookup(self, appids: Iterable[int], max_batches: int | None = None) -> dict[int, PriceSnapshot]: ...


class PriceService:
    def __init__(
        self,
        sessionmaker: Callable[[], async_sessionmaker[AsyncSession]],
        store: StoreApi,
        limiter: TokenBucket,
        policy: PricePolicy,
        cc: str,
        rate_limit_pause_seconds: float = 60,
        batch_size: int = BATCH_SIZE,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessionmaker = sessionmaker
        self._store = store
        self._limiter = limiter
        self._policy = policy
        self._cc = cc
        self._pause_seconds = rate_limit_pause_seconds
        self._batch_size = batch_size
        self._now = now
        # 동시에 들어온 요청이 같은 게임을 중복 조회하지 않게 한다(단일 인스턴스 전제).
        self._inflight: set[int] = set()

    async def lookup(self, appids: Iterable[int], max_batches: int | None = None) -> dict[int, PriceSnapshot]:
        ids = sorted(set(appids))
        if not ids:
            return {}
        async with self._sessionmaker()() as session:
            rows = await self._read(session, ids)
            now = self._now()
            due = [a for a in ids if a not in self._inflight and _is_due(rows.get(a), now)]
            batches = [due[i : i + self._batch_size] for i in range(0, len(due), self._batch_size)]
            if max_batches is not None:
                batches = batches[:max_batches]
            claimed = {a for batch in batches for a in batch}
            self._inflight |= claimed
            try:
                for batch in batches:
                    rate_limited = await self._fetch(session, batch, rows)
                    if rate_limited:
                        break  # 남은 묶음은 다음 요청으로 미룬다
                if claimed:
                    rows = await self._read(session, ids)
            finally:
                self._inflight -= claimed
        return {a: rows.get(a) or PriceSnapshot(a, FetchStatus.PENDING) for a in ids}

    async def _read(self, session: AsyncSession, ids: list[int]) -> dict[int, PriceSnapshot]:
        result = await session.scalars(select(GamePrice).where(GamePrice.cc == self._cc, GamePrice.appid.in_(ids)))
        return {row.appid: _snapshot(row) for row in result}

    async def _fetch(self, session: AsyncSession, batch: list[int], current: dict[int, PriceSnapshot]) -> bool:
        """한 묶음을 받아 저장한다. 상점이 제한을 걸었으면 True."""
        await self._limiter.acquire()
        results = await self._store.prices(batch, self._cc)
        rate_limited = any(r.outcome is Outcome.RATE_LIMITED for r in results.values())
        if rate_limited:
            logger.warning("store rate limited on prices, pausing %ss", self._pause_seconds)
            self._limiter.pause(self._pause_seconds)
        now = self._now()
        for appid in batch:
            values = _apply(results[appid], current.get(appid), now, self._policy)
            await session.execute(
                insert(GamePrice)
                .values(appid=appid, cc=self._cc, **{"fetch_status": FetchStatus.PENDING, **values})
                .on_conflict_do_update(index_elements=["appid", "cc"], set_=values)
            )
        await session.commit()
        return rate_limited


def _is_due(snap: PriceSnapshot | None, now: datetime) -> bool:
    return snap is None or snap.due_at is None or snap.due_at <= now


def _snapshot(row: GamePrice) -> PriceSnapshot:
    due = row.retry_after if row.fetch_status is FetchStatus.TEMPORARY_ERROR else row.expires_at
    return PriceSnapshot(
        appid=row.appid,
        status=row.fetch_status,
        currency=row.currency,
        initial_price=row.initial_price,
        final_price=row.final_price,
        discount_percent=row.discount_percent,
        fetched_at=row.fetched_at,
        due_at=due,
    )


def _apply(result: PriceResult, previous: PriceSnapshot | None, now: datetime, policy: PricePolicy) -> dict[str, Any]:
    """조회 결과로 game_price에 쓸 컬럼 값. 일시 실패는 절대 NOT_AVAILABLE이 되지 않는다."""
    if result.outcome is Outcome.OK:
        p = result.price
        return {
            "currency": p.currency if p else None,
            "initial_price": p.initial if p else None,
            "final_price": p.final if p else None,
            "discount_percent": p.discount_percent if p else None,
            "fetch_status": FetchStatus.SUCCESS,
            "fetched_at": now,
            "expires_at": now + policy.ttl,
            "retry_after": None,
            "failure_reason": None,
        }
    if result.outcome is Outcome.NOT_FOUND:
        # 가격 캐시는 TTL이 짧아 메타데이터처럼 재확인 단계를 두지 않는다(1시간 뒤 다시 확인).
        return {
            "fetch_status": FetchStatus.NOT_AVAILABLE,
            "expires_at": now + policy.retry_not_found,
            "retry_after": None,
            "failure_reason": result.reason,
        }
    retry_at = now + (policy.retry_rate_limited if result.outcome is Outcome.RATE_LIMITED else policy.retry_error)
    if previous is not None and previous.status is FetchStatus.SUCCESS:
        # 이미 받은 가격은 유지하고 나중에 다시 시도한다.
        return {"expires_at": retry_at, "failure_reason": result.reason}
    return {"fetch_status": FetchStatus.TEMPORARY_ERROR, "retry_after": retry_at, "failure_reason": result.reason}
