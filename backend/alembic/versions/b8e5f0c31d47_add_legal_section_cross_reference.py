"""add legal_sections.cross_reference

Adds a nullable JSONB column holding the AI-suggested pre-2024 equivalent
(IPC / CrPC / Evidence Act) for each new-law section, or NULL when none is
confidently known. Additive + nullable, so existing rows are untouched.

Revision ID: b8e5f0c31d47
Revises: a7d21e4c9b30
Create Date: 2026-07-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8e5f0c31d47'
down_revision: Union[str, Sequence[str], None] = 'a7d21e4c9b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "legal_sections",
        sa.Column("cross_reference", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("legal_sections", "cross_reference")
