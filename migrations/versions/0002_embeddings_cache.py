"""embeddings cache table

Revision ID: 0002_embeddings_cache
Revises: 0001_initial
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_embeddings_cache"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embeddings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("vector", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("embeddings")
