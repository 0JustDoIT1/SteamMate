"""게임 메타데이터 캐시 서비스.

lookup()은 DB에 있는 값을 즉시 돌려주고, 없거나 오래된 게임은 백그라운드 대기열에 넣는다(부분 응답).
대기열은 우선순위가 있다: 사용자 요청(HIGH)이 수집 작업이 넣은 항목(LOW)보다 먼저 처리된다.
워커는 레이트리미터를 지키며 Steam 상점에서 받아 상태 전이 규칙대로 저장한다.
단일 인스턴스 전제: 대기열·진행 중 목록은 프로세스 메모리에 있다.
"""

import asyncio
import itertools
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.rate_limit import TokenBucket
from app.metadata.state import (
    NO_GENRES_REASON,
    MetadataPolicy,
    PreviousState,
    apply_result,
    is_due,
)
from app.models import FetchStatus, GameMetadata
from app.steam.store_api import Outcome, StoreApi

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    HIGH = 0  # 사용자 화면에 바로 필요한 게임
    LOW = 1  # 수집 작업이 미리 채우는 게임


@dataclass(frozen=True)
class MetadataSnapshot:
    """세션과 분리된 읽기 전용 값(ORM 객체를 밖으로 내보내지 않는다)."""

    appid: int
    status: FetchStatus
    app_type: str | None = None
    genres: tuple[str, ...] = ()
    fetched_at: datetime | None = None
    name: str | None = None
    header_image: str | None = None
    dlc_appids: tuple[int, ...] = ()


class MetadataLookup(Protocol):
    async def lookup(
        self, appids: Iterable[int], priority: Priority = Priority.HIGH
    ) -> dict[int, MetadataSnapshot]: ...


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
        self._queue: asyncio.PriorityQueue[tuple[int, int, int]] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._queued: dict[int, Priority] = {}  # 대기 중(아직 시작 안 함)인 게임과 그 우선순위
        self._started: set[int] = set()  # 처리 중인 게임
        # 처리를 마친 순번. lookup이 DB를 읽기 시작한 뒤에 처리가 끝난 게임은 읽은 행이 옛 상태라
        # 다시 넣지 않는다(동시 lookup의 중복 요청 방지). 게임 수만큼만 커진다.
        self._finished = 0
        self._finished_at: dict[int, int] = {}
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

    async def lookup(
        self, appids: Iterable[int], priority: Priority = Priority.HIGH
    ) -> dict[int, MetadataSnapshot]:
        ids = sorted(set(appids))
        if not ids:
            return {}
        now = self._now()
        read_from = self._finished
        async with self._sessionmaker()() as session:
            rows = {
                row.appid: row
                for row in (await session.scalars(select(GameMetadata).where(GameMetadata.appid.in_(ids))))
            }
            to_queue = [a for a in ids if self._should_queue(a, rows.get(a), now, priority, read_from)]
            new_ids = [a for a in to_queue if a not in rows]
            if new_ids:
                # 처음 보는 게임은 PENDING 행을 만든다. 다른 요청이 먼저 넣었으면 건드리지 않는다.
                await session.execute(
                    insert(GameMetadata)
                    .values(
                        [{"appid": a, "fetch_status": FetchStatus.PENDING, "last_checked_at": now} for a in new_ids]
                    )
                    .on_conflict_do_nothing(index_elements=["appid"])
                )
            stale_pending = [a for a in to_queue if a in rows and rows[a].fetch_status is FetchStatus.PENDING]
            for appid in stale_pending:
                rows[appid].last_checked_at = now
            if new_ids or stale_pending:
                await session.commit()

            snapshots = {appid: _snapshot(row) for appid, row in rows.items()}

        for appid in new_ids:
            snapshots[appid] = MetadataSnapshot(appid=appid, status=FetchStatus.PENDING)
        for appid in to_queue:
            # 판단 후 DB 저장을 기다리는 사이 다른 lookup이 넣었거나 처리했을 수 있다.
            # 여기서부터 put까지는 await가 없어 다시 확인한 결과가 그대로 유지된다.
            # DB 행은 다시 보지 않는다(위에서 stale PENDING의 last_checked_at을 이미 갱신했다).
            if self._memory_decision(appid, priority, read_from) is False:
                continue
            self._queued[appid] = priority
            self._queue.put_nowait((priority, next(self._seq), appid))
        return snapshots

    def _should_queue(
        self, appid: int, row: GameMetadata | None, now: datetime, priority: Priority, read_from: int
    ) -> bool:
        decided = self._memory_decision(appid, priority, read_from)
        return _row_is_due(row, now, self._policy) if decided is None else decided

    def _memory_decision(self, appid: int, priority: Priority, read_from: int) -> bool | None:
        """처리 중·대기 중·방금 처리됨 상태로 정해지면 True/False, DB 행을 봐야 하면 None."""
        if appid in self._started or self._finished_at.get(appid, -1) > read_from:
            return False
        queued = self._queued.get(appid)
        if queued is not None:
            # 이미 대기 중이면 더 높은 우선순위 요청일 때만 다시 넣는다(앞당기기).
            return priority < queued
        return None

    async def _worker(self) -> None:
        while True:
            priority, _, appid = await self._queue.get()
            started = False
            try:
                if self._queued.get(appid) != priority:
                    continue  # 우선순위가 올라가 다시 들어간 항목의 옛 사본
                del self._queued[appid]
                self._started.add(appid)
                started = True
                await self._refresh(appid)
            except asyncio.CancelledError:
                raise
            except Exception:
                # 한 게임의 실패가 워커를 멈추지 않게 한다. 행은 PENDING으로 남아 stale 복구 대상이 된다.
                logger.exception("metadata refresh failed: appid=%s", appid)
            finally:
                if started:  # 옛 사본은 다른 작업자가 처리 중인 표시를 지우면 안 된다
                    self._started.discard(appid)
                    self._finished += 1
                    self._finished_at[appid] = self._finished
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
    if row.header_image is None and (
        row.fetch_status is FetchStatus.SUCCESS
        or (row.fetch_status is FetchStatus.NOT_AVAILABLE and row.failure_reason == NO_GENRES_REASON)
    ):
        # header_image 컬럼 추가(02b117ec3418) 이전에 받은 정상 응답 행을 한 번 보충한다.
        # (장르만 없는 NOT_AVAILABLE도 상점 응답에 이미지 주소가 있다)
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
        name=row.name,
        header_image=row.header_image,
        dlc_appids=tuple(row.dlc_appids_json or ()),
    )
