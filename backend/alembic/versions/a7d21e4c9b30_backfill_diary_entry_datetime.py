"""backfill case_diary_entries.entry_datetime from created_at

Auto-generated diary entries used to be written with entry_datetime NULL (only the
handful of manually-created entries carried one). GET /cases/{id} orders the diary by
entry_datetime, so those rows rendered with blank dates in an undefined order.

The write paths now always set entry_datetime. This backfills the historical rows from
created_at, which is the closest available record of when the entry was written.

Revision ID: a7d21e4c9b30
Revises: 0eafd4b051a3
Create Date: 2026-07-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7d21e4c9b30'
down_revision: Union[str, Sequence[str], None] = '0eafd4b051a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # created_at is server_default now(), so it is never NULL — COALESCE to now() only
    # as a belt-and-braces guard for any row predating that default.
    op.execute(
        """
        UPDATE case_diary_entries
           SET entry_datetime = COALESCE(created_at, now())
         WHERE entry_datetime IS NULL
        """
    )


def downgrade() -> None:
    # The pre-backfill state (which rows were NULL) is not recoverable, and restoring
    # NULLs would reintroduce the blank-date bug. Intentionally a no-op.
    pass
