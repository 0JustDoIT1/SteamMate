"""ORM 모델. PostgreSQL에는 공개 게임 데이터만 저장한다(사용자 데이터와 연결하지 않음)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
    genres_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    categories_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    dlc_appids_json: Mapped[list[int] | None] = mapped_column(JSONB)
    fetch_status: Mapped[FetchStatus] = mapped_column(fetch_status_enum, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(String(64))
