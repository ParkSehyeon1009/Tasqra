"""store document processing failure reason

Revision ID: 20260814_0013
Revises: 20260814_0012
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0013"
down_revision = "20260814_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("processing_error", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "processing_error")
