"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-16
"""

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    import app.models.payslip  # noqa: F401
    import app.models.user  # noqa: F401
    from app.db.base import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    import app.models.payslip  # noqa: F401
    import app.models.user  # noqa: F401
    from app.db.base import Base

    Base.metadata.drop_all(bind=op.get_bind())
