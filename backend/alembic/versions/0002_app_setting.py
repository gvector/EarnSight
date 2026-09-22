"""app_setting table

Revision ID: 0002_app_setting
Revises: 0001_initial
Create Date: 2026-09-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_app_setting"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, unique=True),
        sa.Column("llm_provider", sa.String(16), nullable=True),
        sa.Column("ollama_base_url", sa.String(256), nullable=True),
        sa.Column("ollama_model", sa.String(64), nullable=True),
        sa.Column("openai_model", sa.String(64), nullable=True),
        sa.Column("openai_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
