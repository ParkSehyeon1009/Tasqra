"""add staged OCR text exclusion"""
from alembic import op
import sqlalchemy as sa

revision = "20260812_0008"
down_revision = "20260811_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ocr_elements", sa.Column("is_excluded", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("ocr_elements", "is_excluded")
