"""create chart snapshot tables

Revision ID: eb78d475c786
Revises: 25542961bbf2
Create Date: 2026-11-03 06:13:13.906326

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "eb78d475c786"
down_revision: str | Sequence[str] | None = "25542961bbf2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

chart_source = postgresql.ENUM(
    "TOP_SELLERS", "MOST_PLAYED", "CONCURRENT", "SPECIALS", "NEW_RELEASES", name="chart_source"
)
snapshot_status = postgresql.ENUM("SUCCESS", "FAILED", name="snapshot_status")


def upgrade() -> None:
    op.create_table(
        "chart_snapshot",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("source", chart_source, nullable=False),
        sa.Column("cc", sa.String(length=8), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", snapshot_status, nullable=False),
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chart_snapshot_source_captured", "chart_snapshot", ["source", "cc", "captured_at"], unique=False
    )
    op.create_table(
        "chart_entry",
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("appid", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("last_week_rank", sa.Integer(), nullable=True),
        sa.Column("metric_value", sa.BigInteger(), nullable=True),
        sa.Column("final_price", sa.BigInteger(), nullable=True),
        sa.Column("original_price", sa.BigInteger(), nullable=True),
        sa.Column("discount_percent", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["chart_snapshot.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id", "rank"),
    )
    op.create_index(op.f("ix_chart_entry_appid"), "chart_entry", ["appid"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chart_entry_appid"), table_name="chart_entry")
    op.drop_table("chart_entry")
    op.drop_index("ix_chart_snapshot_source_captured", table_name="chart_snapshot")
    op.drop_table("chart_snapshot")
    # enum 타입은 테이블과 별개 객체라 명시적으로 지워야 재적용(up)이 가능하다.
    snapshot_status.drop(op.get_bind(), checkfirst=True)
    chart_source.drop(op.get_bind(), checkfirst=True)
