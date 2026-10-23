"""init datasources and models

Revision ID: 20261023_0001
Revises:
Create Date: 2026-10-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261023_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aigc_datasource",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("db_type", sa.String(length=32), nullable=False, server_default="mysql"),
        sa.Column("host", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("password", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("jdbc_url", sa.Text(), nullable=True),
        sa.Column("structure_json", sa.JSON(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "aigc_model",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="openai-compatible"),
        sa.Column("base_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("api_key", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("aigc_model")
    op.drop_table("aigc_datasource")
