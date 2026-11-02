"""게임 메타데이터 캐시 서비스.

lookup()은 DB에 있는 값을 즉시 돌려주고, 없거나 오래된 게임은 백그라운드 대기열에 넣는다(부분 응답).
워커는 레이트리미터를 지키며 Steam 상점에서 받아 상태 전이 규칙대로 저장한다.
단일 인스턴스 전제: 진행 중 목록(_inflight)과 대기열은 프로세스 메모리에 있다.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.rate_limit import TokenBucket
from app.metadata.state import MetadataPolicy, PreviousState, apply_result, is_due
from app.models import FetchStatus, GameMetadata
from app.steam.store_api import Outcome, StoreApi

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetadataSnapshot:
    """세션과 분리된 읽기 전용 값(ORM 객체를 밖으로 내보내지 않는다)."""

    appid: int
    status: FetchStatus
    app_type: str | None = None
    genres: tuple[str, ...] = ()
    fetched_at: datetime | None = None


class MetadataLookup(Protocol):
    async def lookup(self, appids: Iterable[int]) -> dict[int, MetadataSnapshot]: ...


class MetadataService:
    def __init__(
        self,
        sessionmaker: Callable[[], async_sessionmaker[AsyncSession]],
        store: StoreApi,
        limiter: TokenBucket,
        policy: MetadataPolicy,
        *,
        concurrency: int,
        rate_limit_pause_seconds: float,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessionmaker = sessionmaker
        self._store = store
        self._limiter = limiter
        self._policy = policy
        self._concurrency = concurrency
        self._pause_seconds = rate_limit_pause_seconds
        self._now = now
        self._queue: asyncio.Queue[int] = asyncio.Queue()
        self._inflight: set[int] = set()
        self._workers: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if not self._workers:
            self._workers = [asyncio.create_task(self._worker()) for _ in range(self._concurrency)]

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    async def drain(self) -> None:
        """대기열이 빌 때까지 기다린다(테스트·수동 실행용)."""
        await self._queue.join()

    async def lookup(self, appids: Iterable[int]) -> dict[int, MetadataSnapshot]:
        ids = sorted(set(appids))
        if not ids:
            return {}
        now = self._now()
        async with self._sessionmaker()() as session:
            rows = {
                row.appid: row
                for row in (await session.scalars(select(GameMetadata).where(GameMetadata.appid.in_(ids))))
            }
            due = [
                appid
                for appid in ids
                if appid not in self._inflight and _row_is_due(rows.get(appid), now, self._policy)
            ]
            new_ids = [appid for appid in due if appid not in rows]
            if new_ids:
                # 처음 보는 게임은 PENDING 행을 만든다. 다른 요청이 먼저 넣었으면 건드리지 않는다.
                await session.execute(
                    insert(GameMetadata)
                    .values(
                        [
                            {"appid": a, "fetch_status": FetchStatus.PENDING, "last_checked_at": now}
                            for a in new_ids
                        ]
                    )
                    .on_conflict_do_nothing(index_elements=["appid"])
                )
            if due:
                pending_stale = [a for a in due if a in rows and rows[a].fetch_status is FetchStatus.PENDING]
                for appid in pending_stale:
                    rows[appid].last_checked_at = now
                await session.commit()

            snapshots = {appid: _snapshot(row) for appid, row in rows.items()}

        for appid in new_ids:
            snapshots[appid] = MetadataSnapshot(appid=appid, status=FetchStatus.PENDING)
        for appid in due:
            self._inflight.add(appid)
            self._queue.put_nowait(appid)
        return snapshots

    async def _worker(self) -> None:
        while True:
            appid = await self._queue.get()
            try:
                await self._refresh(appid)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 한 게임의 실패가 워커를 멈추지 않게 한다. 행은 PENDING으로 남아 stale 복구 대상이 된다.
                logger.exception("metadata refresh failed: appid=%s", appid)
            finally:
                self._inflight.discard(appid)
                self._queue.task_done()

    async def _refresh(self, appid: int) -> None:
        await self._limiter.acquire()
        result = await self._store.app_details(appid)
        if result.outcome is Outcome.RATE_LIMITED:
            logger.warning("store rate limited, pausing %ss", self._pause_seconds)
            self._limiter.pause(self._pause_seconds)

        async with self._sessionmaker()() as session:
            row = await session.get(GameMetadata, appid)
            previous = PreviousState(row.fetch_status, row.failure_reason) if row else None
            values = apply_result(result, previous, self._now(), self._policy)
            await session.execute(
                insert(GameMetadata)
                .values(appid=appid, **{"fetch_status": FetchStatus.PENDING, **values})
                .on_conflict_do_update(index_elements=["appid"], set_=values)
            )
            await session.commit()


def _row_is_due(row: GameMetadata | None, now: datetime, policy: MetadataPolicy) -> bool:
    if row is None:
        return True
    return is_due(
        row.fetch_status,
        expires_at=row.expires_at,
        retry_after=row.retry_after,
        last_checked_at=row.last_checked_at,
        now=now,
        policy=policy,
    )


def _snapshot(row: GameMetadata) -> MetadataSnapshot:
    return MetadataSnapshot(
        appid=row.appid,
        status=row.fetch_status,
        app_type=row.app_type,
        genres=tuple(g.get("description", "") for g in row.genres_json or []),
        fetched_at=row.fetched_at,
    )
