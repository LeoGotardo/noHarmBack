"""date of birth: tb_0.cl_0j

Revision ID: 20260916_03
Revises: 20260916_02
Create Date: 2026-09-16

The account had no age and the app had no way to ask for one, which made the
minimum-age rule in the terms a sentence with nothing behind it.

## Why a date and not a flag

"I am over 18" as a boolean answers the question once, on the day it is ticked,
and can never be re-asked. A date answers it on every day afterwards, survives
a change to `MINIMUM_AGE_YEARS`, and is the only form in which the answer can
be checked rather than taken on trust from a client.

## Self-declared, and that is the ceiling

No identity provider this app uses carries an age: a Firebase ID token has no
such claim, and Sign in with Apple has no equivalent. Google's People API can
return a coarse age range, but only under a restricted scope that needs Google's
own verification review and comes back empty for anyone who did not fill their
birthday in. So this is what the user typed. What it buys is the record that the
question was asked and answered — not proof.

## Encrypted, nullable

Encrypted for the same reason `cl_0c` is: it is an identifier in every data
broker's sense, and this schema does not hold plaintext personal fields. There
is no blind index because nothing ever looks an account up by birth date.

Nullable because every account that already exists was created before the
question was asked, and there is no honest value to backfill. Those accounts
keep working; registration from here on requires the field. Demanding it
retroactively is a product decision, and the column being nullable is what
leaves that decision open.
"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


revision = "20260916_03"
down_revision = "20260916_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tb_0",
        sa.Column(
            "cl_0j",
            sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Every declared birth date is lost; accounts keep working, and the age
    # check has nothing to read, exactly as before this column existed.
    op.drop_column("tb_0", "cl_0j")
