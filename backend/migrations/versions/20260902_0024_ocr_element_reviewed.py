"""OCR 영역별 검토 완료 상태.

Revision ID: 20260902_0024
Revises: 20260831_0023
"""
import sqlalchemy as sa
from alembic import op

revision = "20260902_0024"
down_revision = "20260831_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocr_elements", sa.Column("is_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("ocr_elements", "is_reviewed")
