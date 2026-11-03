"""create game_price

Revision ID: d4e080ca6206
Revises: 02b117ec3418
Create Date: 2026-11-03 20:48:20.677218

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e080ca6206"
down_revision: str | Sequence[str] | None = "02b117ec3418"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# game_metadata(25542961bbf2)가 만든 타입을 함께 쓴다. 여기서 만들거나 지우지 않는다.
fetch_status = postgresql.ENUM(
    "PENDING", "SUCCESS", "TEMPORARY_ERROR", "NOT_AVAILABLE", name="fetch_status", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "game_price",
        sa.Column("appid", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("cc", sa.String(length=8), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("initial_price", sa.BigInteger(), nullable=True),
        sa.Column("final_price", sa.BigInteger(), nullable=True),
        sa.Column("discount_percent", sa.Integer(), nullable=True),
        sa.Column("fetch_status", fetch_status, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("appid", "cc"),
    )


def downgrade() -> None:
    op.drop_table("game_price")
