"""액션 태스크 CRUD 기반

Revision ID: 20260824_0019
Revises: 20260821_0018
"""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0019"
down_revision = "20260821_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("type", sa.String(20), server_default="OTHER", nullable=False),
        sa.Column("status", sa.String(20), server_default="TODO", nullable=False),
        sa.Column("assignee_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("due_on", sa.Date()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('TODO', 'IN_PROGRESS', 'DONE')", name="ck_task_status"),
        sa.CheckConstraint("type IN ('DEVELOPMENT', 'DESIGN', 'INFRA', 'DOCUMENT', 'OTHER')", name="ck_task_type"),
    )
    op.create_index("ix_task_project_status", "tasks", ["project_id", "status"])
    op.create_index("ix_task_project_due", "tasks", ["project_id", "due_on"])
    op.create_index("ix_task_assignee", "tasks", ["assignee_id"])


def downgrade() -> None:
    op.drop_index("ix_task_assignee", table_name="tasks")
    op.drop_index("ix_task_project_due", table_name="tasks")
    op.drop_index("ix_task_project_status", table_name="tasks")
    op.drop_table("tasks")
