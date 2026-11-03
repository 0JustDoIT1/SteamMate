"""ORM 모델. PostgreSQL에는 공개 게임 데이터만 저장한다(사용자 데이터와 연결하지 않음)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FetchStatus(StrEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    TEMPORARY_ERROR = "TEMPORARY_ERROR"
    NOT_AVAILABLE = "NOT_AVAILABLE"


fetch_status_enum = Enum(
    FetchStatus,
    name="fetch_status",
    values_callable=lambda members: [m.value for m in members],
)


class GameMetadata(Base):
    """게임 1개 = 1행. Steam 상점에 공개된 정보만 담는 공용 캐시."""

    __tablename__ = "game_metadata"

    appid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str | None] = mapped_column(Text)
    app_type: Mapped[str | None] = mapped_column(String(32))
    # 헤더 이미지 주소(URL)만 저장한다. 이미지는 브라우저가 Steam CDN에서 직접 받는다.
    header_image: Mapped[str | None] = mapped_column(Text)
    genres_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    categories_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    dlc_appids_json: Mapped[list[int] | None] = mapped_column(JSONB)
    fetch_status: Mapped[FetchStatus] = mapped_column(fetch_status_enum, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(64))


class GamePrice(Base):
    """(게임, 상점 국가) = 1행. 상점 가격의 단기 캐시(TTL 1시간, 임시). 사용자 정보와 연결하지 않는다.

    가격이 없는 정상 응답(무료·미출시·가격 미정)은 SUCCESS + 가격 NULL로 둔다(`has_price` False).
    """

    __tablename__ = "game_price"

    appid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    cc: Mapped[str] = mapped_column(String(8), primary_key=True)
    currency: Mapped[str | None] = mapped_column(String(8))
    # Steam 최소 단위×100(예: KRW 1100000 = ₩11,000)
    initial_price: Mapped[int | None] = mapped_column(BigInteger)
    final_price: Mapped[int | None] = mapped_column(BigInteger)
    discount_percent: Mapped[int | None] = mapped_column(Integer)
    fetch_status: Mapped[FetchStatus] = mapped_column(fetch_status_enum, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(64))


class ChartSource(StrEnum):
    TOP_SELLERS = "TOP_SELLERS"  # 주간 판매 순위(전 세계)
    MOST_PLAYED = "MOST_PLAYED"  # 주간 최다 플레이(전 세계)
    CONCURRENT = "CONCURRENT"  # 현재 동시 접속(전 세계)
    SPECIALS = "SPECIALS"  # 상점 할인 기획(국가별)
    NEW_RELEASES = "NEW_RELEASES"  # 상점 신작 기획(국가별)


class SnapshotStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


def _pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda members: [m.value for m in members])


class ChartSnapshot(Base):
    """한 번의 수집 결과. 공개 집계 데이터만 담으며 보관 기간이 지나면 삭제한다."""

    __tablename__ = "chart_snapshot"
    __table_args__ = (Index("ix_chart_snapshot_source_captured", "source", "cc", "captured_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[ChartSource] = mapped_column(_pg_enum(ChartSource, "chart_source"), nullable=False)
    cc: Mapped[str] = mapped_column(String(8), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Steam 주간 집계 기준일(주간 차트만). 같으면 새 스냅샷을 만들지 않는다.
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SnapshotStatus] = mapped_column(_pg_enum(SnapshotStatus, "snapshot_status"), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(64))

    entries: Mapped[list["ChartEntry"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", passive_deletes=True, order_by="ChartEntry.rank"
    )


class ChartEntry(Base):
    __tablename__ = "chart_entry"

    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chart_snapshot.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer, primary_key=True)
    appid: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(Text)
    last_week_rank: Mapped[int | None] = mapped_column(Integer)
    # TOP_SELLERS=연속 순위권 주 수, MOST_PLAYED=주간 최고 동시 접속, CONCURRENT=현재 동시 접속
    metric_value: Mapped[int | None] = mapped_column(BigInteger)
    # 가격은 Steam 최소 단위(예: KRW 1100000 = ₩11,000)
    final_price: Mapped[int | None] = mapped_column(BigInteger)
    original_price: Mapped[int | None] = mapped_column(BigInteger)
    discount_percent: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(8))
    image_url: Mapped[str | None] = mapped_column(Text)

    snapshot: Mapped[ChartSnapshot] = relationship(back_populates="entries")
