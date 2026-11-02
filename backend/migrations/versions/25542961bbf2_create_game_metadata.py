"""create game_metadata

Revision ID: 25542961bbf2
Revises:
Create Date: 2026-11-03 05:58:09.261015

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "25542961bbf2"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

fetch_status = postgresql.ENUM(
    "PENDING", "SUCCESS", "TEMPORARY_ERROR", "NOT_AVAILABLE", name="fetch_status"
)


def upgrade() -> None:
    op.create_table(
        "game_metadata",
        sa.Column("appid", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("app_type", sa.String(length=32), nullable=True),
        sa.Column("genres_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("categories_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dlc_appids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetch_status", fetch_status, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("appid"),
    )


def downgrade() -> None:
    op.drop_table("game_metadata")
    # enum 타입은 테이블과 별개 객체라 명시적으로 지워야 재적용(up)이 가능하다.
    fetch_status.drop(op.get_bind(), checkfirst=True)
