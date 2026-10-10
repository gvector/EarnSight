"""Campi fiscali: imponibile IRPEF, IRPEF trattenuta, codice fiscale del datore

Revision ID: 0004_fiscal_fields
Revises: 0003_document_user_required
Create Date: 2026-10-10

Colonne dedicate per le analisi (somme per anno e per datore di lavoro). I
progressivi annui restano solo nel JSONB. I documenti esistenti le ricevono
con «Rielabora»: nessun backfill.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_fiscal_fields"
down_revision = "0003_document_user_required"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payslip_document", sa.Column("taxable_income", sa.Numeric(12, 2), nullable=True))
    op.add_column("payslip_document", sa.Column("income_tax", sa.Numeric(12, 2), nullable=True))
    op.add_column("payslip_document", sa.Column("employer_tax_code", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("payslip_document", "employer_tax_code")
    op.drop_column("payslip_document", "income_tax")
    op.drop_column("payslip_document", "taxable_income")
