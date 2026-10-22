"""servers

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 00:33:28.071957
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "servers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("memory", sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column("image_tag", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("server_type", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("version", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("motd", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
        sa.Column("extra_env", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("port"),
    )


def downgrade() -> None:
    op.drop_table("servers")
