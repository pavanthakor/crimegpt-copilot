"""add LERS preservation and records doc types

Revision ID: 0eafd4b051a3
Revises: 1c03b87a1f78
Create Date: 2026-07-20 00:07:51.078749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0eafd4b051a3'
down_revision: Union[str, Sequence[str], None] = '1c03b87a1f78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `ALTER TYPE ... ADD VALUE` has transaction restrictions in PostgreSQL: the new label
    # cannot be used in the same transaction that adds it, and older versions reject the
    # statement inside a transaction block entirely. Alembic's autocommit_block() commits
    # the current transaction and runs the DDL outside it, which is safe across versions.
    # IF NOT EXISTS keeps this idempotent (safe to re-run).
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE doctype ADD VALUE IF NOT EXISTS 'LERS_PRESERVATION_REQUEST'")
        op.execute("ALTER TYPE doctype ADD VALUE IF NOT EXISTS 'LERS_RECORDS_REQUEST'")


def downgrade() -> None:
    # No-op by design: PostgreSQL has no `ALTER TYPE ... DROP VALUE`, so an enum label
    # cannot be removed. Reverting would require recreating the `doctype` type and rewriting
    # every dependent column — unsafe to automate here. Intentionally left empty.
    pass
