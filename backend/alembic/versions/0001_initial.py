"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
    )
    op.create_index("ix_user_username", "user", ["username"], unique=True)

    op.create_table(
        "payslip_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("doc_type", sa.String(16), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("stored_path", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("template", sa.String(64), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("extraction", postgresql.JSONB(), nullable=True),
        sa.Column("period_month", sa.Integer(), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=True),
        sa.Column("gross_pay", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_pay", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_deductions", sa.Numeric(12, 2), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payslip_document_user_id", "payslip_document", ["user_id"])
    op.create_index("ix_payslip_document_status", "payslip_document", ["status"])

    op.create_table(
        "payslip_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("payslip_document.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(16), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("entry_type", sa.String(16), nullable=False),
    )
    op.create_index("ix_payslip_entry_document_id", "payslip_entry", ["document_id"])


def downgrade() -> None:
    op.drop_table("payslip_entry")
    op.drop_table("payslip_document")
    op.drop_table("user")
