"""allow canceled project invitations"""
from alembic import op

revision = "20260811_0005"
down_revision = "20260811_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_invitation_status", "project_invitations", type_="check")
    op.create_check_constraint("ck_invitation_status", "project_invitations", "status IN ('PENDING', 'ACCEPTED', 'DECLINED', 'CANCELED')")


def downgrade():
    op.execute("UPDATE project_invitations SET status = 'DECLINED' WHERE status = 'CANCELED'")
    op.drop_constraint("ck_invitation_status", "project_invitations", type_="check")
    op.create_check_constraint("ck_invitation_status", "project_invitations", "status IN ('PENDING', 'ACCEPTED', 'DECLINED')")
