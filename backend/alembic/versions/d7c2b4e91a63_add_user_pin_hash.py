"""add user pin_hash

Revision ID: d7c2b4e91a63
Revises: e1f7a3c95d80
Create Date: 2026-08-02 21:18:44.207913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7c2b4e91a63'
down_revision: Union[str, Sequence[str], None] = 'e1f7a3c95d80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A per-officer PIN for stepping up to a high-stakes action — registering a case,
    # finalizing a document. Attributable to the individual officer, so the audit trail
    # names a person and not a shared code.
    #
    # HASHED, NEVER STORED IN THE CLEAR. The column holds a bcrypt digest produced by the
    # same core.security.hash_password() that already hashes passwords; nothing new is
    # introduced to get it wrong, and the plaintext PIN exists only in the request that
    # verifies it.
    #
    # Nullable because an account without a PIN is a real state: existing rows have none
    # until one is set, and the seed populates the demo officers separately. What a null
    # means for the gate is a policy decision for the wiring phase, not for the schema.
    op.add_column("users", sa.Column("pin_hash", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "pin_hash")
