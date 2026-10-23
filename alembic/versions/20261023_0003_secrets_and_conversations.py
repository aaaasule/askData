"""widen secret columns and store analysis conversations

Revision ID: 20261023_0003
Revises: 20261023_0002
Create Date: 2026-10-23

Ciphertext is longer than a typical password, so the secret columns become
TEXT. Conversation rows are new; existing plaintext secrets stay readable
until the application rewrites them on read.

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261023_0003"
down_revision: str | None = "20261023_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("aigc_datasource") as batch:
        batch.alter_column(
            "password",
            existing_type=sa.String(length=512),
            type_=sa.Text(),
            existing_nullable=False,
            existing_server_default="",
        )
    with op.batch_alter_table("aigc_model") as batch:
        batch.alter_column(
            "api_key",
            existing_type=sa.String(length=512),
            type_=sa.Text(),
            existing_nullable=False,
            existing_server_default="",
        )
    op.create_table(
        "aigc_conversation",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("datasource_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_aigc_conversation_datasource_id",
        "aigc_conversation",
        ["datasource_id"],
    )
    op.create_table(
        "aigc_message",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_aigc_message_conversation_id",
        "aigc_message",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_aigc_message_conversation_id", table_name="aigc_message")
    op.drop_table("aigc_message")
    op.drop_index("ix_aigc_conversation_datasource_id", table_name="aigc_conversation")
    op.drop_table("aigc_conversation")
    with op.batch_alter_table("aigc_model") as batch:
        batch.alter_column(
            "api_key",
            existing_type=sa.Text(),
            type_=sa.String(length=512),
            existing_nullable=False,
            existing_server_default="",
        )
    with op.batch_alter_table("aigc_datasource") as batch:
        batch.alter_column(
            "password",
            existing_type=sa.Text(),
            type_=sa.String(length=512),
            existing_nullable=False,
            existing_server_default="",
        )
