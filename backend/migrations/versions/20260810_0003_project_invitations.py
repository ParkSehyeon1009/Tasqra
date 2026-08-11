"""add project invitations"""
from alembic import op
import sqlalchemy as sa

revision = "20260810_0003"
down_revision = "20260810_0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("project_invitations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invitee_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "invitee_id", name="uq_project_invitee"),
        sa.CheckConstraint("role IN ('EDITOR', 'VIEWER')", name="ck_invitation_role"),
        sa.CheckConstraint("status IN ('PENDING', 'ACCEPTED', 'DECLINED')", name="ck_invitation_status"),
    )
    op.create_index("ix_project_invitations_invitee_id", "project_invitations", ["invitee_id"])

def downgrade():
    op.drop_table("project_invitations")
