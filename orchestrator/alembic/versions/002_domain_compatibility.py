"""Add relational fields required by active marketplace behavior.

Revision ID: 002_domain_compatibility
Revises: 001_baseline
Create Date: 2026-09-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_domain_compatibility"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("embedding", postgresql.JSONB(), nullable=True))
    op.add_column(
        "appointment_requests",
        sa.Column("recommendation_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "appointment_requests",
        sa.Column("issue", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointment_requests", "issue")
    op.drop_column("appointment_requests", "recommendation_session_id")
    op.drop_column("products", "embedding")
