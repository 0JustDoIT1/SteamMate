"""add game_metadata header_image

Revision ID: 02b117ec3418
Revises: eb78d475c786
Create Date: 2026-11-03 06:33:47.381034

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02b117ec3418"
down_revision: str | Sequence[str] | None = "eb78d475c786"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 이미지 파일이 아닌 주소(URL)만 저장한다.
    op.add_column("game_metadata", sa.Column("header_image", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_metadata", "header_image")
