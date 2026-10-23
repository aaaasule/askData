"""extend aigc_model with chat sampling fields

Revision ID: 20261023_0002
Revises: 20261023_0001
Create Date: 2026-10-23

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261023_0002"
down_revision: str | None = "20261023_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "aigc_model",
        sa.Column("type", sa.String(length=32), nullable=False, server_default="chat"),
    )
    op.add_column(
        "aigc_model",
        sa.Column("endpoint", sa.String(length=512), nullable=False, server_default=""),
    )
    op.add_column("aigc_model", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("aigc_model", sa.Column("top_p", sa.Float(), nullable=True))
    op.add_column("aigc_model", sa.Column("max_token", sa.Integer(), nullable=True))
    op.add_column("aigc_model", sa.Column("config_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("aigc_model") as batch:
        batch.drop_column("config_json")
        batch.drop_column("max_token")
        batch.drop_column("top_p")
        batch.drop_column("temperature")
        batch.drop_column("endpoint")
        batch.drop_column("type")
