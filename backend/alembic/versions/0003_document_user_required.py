"""payslip_document.user_id NOT NULL

Revision ID: 0003_document_user_required
Revises: 0002_app_setting
Create Date: 2026-10-08

Ogni documento ha un proprietario: il filtro per utente delle route diventa
un vincolo del database. I documenti orfani (user_id NULL) vengono assegnati
all'utente con id minimo — in modalità monoutente è l'admin di bootstrap,
l'unico che può averli caricati. Senza utenti e con orfani presenti la
migrazione si ferma invece di indovinare.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_document_user_required"
down_revision = "0002_app_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    orphans = conn.execute(
        sa.text("SELECT count(*) FROM payslip_document WHERE user_id IS NULL")
    ).scalar_one()
    if orphans:
        owner = conn.execute(sa.text('SELECT min(id) FROM "user"')).scalar_one()
        if owner is None:
            raise RuntimeError(
                f"{orphans} documenti senza proprietario e nessun utente a cui assegnarli"
            )
        conn.execute(
            sa.text("UPDATE payslip_document SET user_id = :owner WHERE user_id IS NULL"),
            {"owner": owner},
        )
    op.alter_column("payslip_document", "user_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.alter_column("payslip_document", "user_id", existing_type=sa.Integer(), nullable=True)
