"""modpack columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22 23:26:38.921837
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("servers", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "modpack",
                sqlmodel.sql.sqltypes.AutoString(length=200),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column(
                "loader",
                sqlmodel.sql.sqltypes.AutoString(length=16),
                nullable=False,
                server_default="",
            )
        )
        batch_op.add_column(
            sa.Column("modpack_zip", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("servers", schema=None) as batch_op:
        batch_op.drop_column("modpack_zip")
        batch_op.drop_column("loader")
        batch_op.drop_column("modpack")
