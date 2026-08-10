"""add separate user login id

Revision ID: 20260810_0002
Revises: 20260810_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260810_0002"
down_revision = "20260810_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("users", sa.Column("login_id", sa.String(50), nullable=True))
    op.execute("UPDATE users SET login_id = lower(email)")
    op.alter_column("users", "login_id", nullable=False)
    op.execute("CREATE UNIQUE INDEX uq_users_login_id_lower ON users (lower(login_id))")

def downgrade():
    op.drop_index("uq_users_login_id_lower", table_name="users")
    op.drop_column("users", "login_id")
