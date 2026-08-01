"""add person chargesheet Form I fields

Adds 17 nullable columns on ``persons`` for Gujarat Police Report to Magistrate
Rules 2025 Form I item 9 (accused particulars). Every column is nullable with
no server default — unknown / not-yet-entered must remain NULL.

``status_of_accused`` is a PostgreSQL ENUM (``accusedstatus``) matching the
existing PersonRole / CaseStatus pattern. Form I item xix values, uppercased:

  FORWARDED | BAILED_BY_POLICE | BAILED_BY_COURT | JUDICIAL_CUSTODY |
  ABSCONDING | PROCLAIMED_OFFENDER

``dob_or_year`` is String (full date OR year). Existing ``age`` Integer is
untouched.

Revision ID: c4f91a2b6e80
Revises: b8e5f0c31d47
Create Date: 2026-07-25 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4f91a2b6e80"
down_revision: Union[str, Sequence[str], None] = "b8e5f0c31d47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Named ENUM — create/drop explicitly so upgrade and downgrade stay paired.
_accusedstatus = sa.Enum(
    "FORWARDED",
    "BAILED_BY_POLICE",
    "BAILED_BY_COURT",
    "JUDICIAL_CUSTODY",
    "ABSCONDING",
    "PROCLAIMED_OFFENDER",
    name="accusedstatus",
)


def upgrade() -> None:
    _accusedstatus.create(op.get_bind(), checkfirst=True)

    op.add_column("persons", sa.Column("dob_or_year", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("nationality", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("address_verified", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("passport_no", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("passport_issue_date", sa.Date(), nullable=True))
    op.add_column("persons", sa.Column("passport_issue_place", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("religion", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("sc_st_obc", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("provisional_criminal_no", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("regular_criminal_no", sa.String(), nullable=True))
    op.add_column("persons", sa.Column("arrest_date", sa.Date(), nullable=True))
    op.add_column("persons", sa.Column("bail_release_date", sa.Date(), nullable=True))
    op.add_column("persons", sa.Column("forwarded_to_court_date", sa.Date(), nullable=True))
    op.add_column("persons", sa.Column("arrest_acts_sections", sa.Text(), nullable=True))
    op.add_column("persons", sa.Column("surety_details", sa.Text(), nullable=True))
    op.add_column("persons", sa.Column("previous_convictions", sa.Text(), nullable=True))
    op.add_column(
        "persons",
        sa.Column("status_of_accused", _accusedstatus, nullable=True),
    )


def downgrade() -> None:
    # Drop exactly the 17 columns this upgrade added — nothing else.
    op.drop_column("persons", "status_of_accused")
    op.drop_column("persons", "previous_convictions")
    op.drop_column("persons", "surety_details")
    op.drop_column("persons", "arrest_acts_sections")
    op.drop_column("persons", "forwarded_to_court_date")
    op.drop_column("persons", "bail_release_date")
    op.drop_column("persons", "arrest_date")
    op.drop_column("persons", "regular_criminal_no")
    op.drop_column("persons", "provisional_criminal_no")
    op.drop_column("persons", "sc_st_obc")
    op.drop_column("persons", "religion")
    op.drop_column("persons", "passport_issue_place")
    op.drop_column("persons", "passport_issue_date")
    op.drop_column("persons", "passport_no")
    op.drop_column("persons", "address_verified")
    op.drop_column("persons", "nationality")
    op.drop_column("persons", "dob_or_year")

    _accusedstatus.drop(op.get_bind(), checkfirst=True)
