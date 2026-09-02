"""Widen users.profile_image_url from VARCHAR(500) to TEXT.

Front-end registration sends base64 data-URIs (~60 KB+) which overflow
the original VARCHAR(500) column, causing StringDataRightTruncationError.

Revision ID: 003_profile_image_text
Revises: 002_domain_compatibility
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_profile_image_text"
down_revision: Union[str, None] = "002_domain_compatibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "profile_image_url",
        type_=sa.Text(),
        existing_type=sa.String(500),
        existing_nullable=True,
    )


def downgrade() -> None:
    # PostgreSQL requires an explicit cast when narrowing TEXT -> VARCHAR(500).
    op.alter_column(
        "users",
        "profile_image_url",
        type_=sa.String(500),
        existing_type=sa.Text(),
        existing_nullable=True,
        postgresql_using="profile_image_url::varchar(500)",
    )
