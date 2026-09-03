"""일정 시각과 상대 기한 보존.

Revision ID: 20260903_0028
Revises: 20260903_0027
"""
import sqlalchemy as sa
from alembic import op

revision = "20260903_0028"
down_revision = "20260903_0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("schedule_items", sa.Column("starts_time", sa.Time(), nullable=True))
    op.add_column("schedule_items", sa.Column("ends_time", sa.Time(), nullable=True))
    op.add_column("schedule_items", sa.Column("relative_expression", sa.String(300), nullable=True))


def downgrade():
    op.drop_column("schedule_items", "relative_expression")
    op.drop_column("schedule_items", "ends_time")
    op.drop_column("schedule_items", "starts_time")
