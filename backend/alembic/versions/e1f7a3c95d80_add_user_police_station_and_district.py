"""add user police_station and district

Revision ID: e1f7a3c95d80
Revises: c4f91a2b6e80
Create Date: 2026-08-02 18:41:12.904617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f7a3c95d80'
down_revision: Union[str, Sequence[str], None] = 'c4f91a2b6e80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The posting an officer is attached to. Conversational intake reads these off the
    # logged-in user to pre-fill a new case header, the way rank/badge_no already feed
    # the IF4 signature block. Nullable so existing rows survive without a backfill —
    # seed.py populates the demo accounts separately.
    op.add_column("users", sa.Column("police_station", sa.String(), nullable=True))
    op.add_column("users", sa.Column("district", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "district")
    op.drop_column("users", "police_station")
