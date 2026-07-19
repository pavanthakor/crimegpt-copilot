"""add user rank and badge_no

Revision ID: 1c03b87a1f78
Revises: 979bae82fe9e
Create Date: 2026-07-19 22:57:01.535345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c03b87a1f78'
down_revision: Union[str, Sequence[str], None] = '979bae82fe9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable so existing seed rows survive without a default backfill.
    op.add_column("users", sa.Column("rank", sa.String(), nullable=True))
    op.add_column("users", sa.Column("badge_no", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "badge_no")
    op.drop_column("users", "rank")
