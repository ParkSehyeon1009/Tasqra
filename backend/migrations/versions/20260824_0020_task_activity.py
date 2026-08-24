"""액션 태스크 생성 경로 및 활동 기록

Revision ID: 20260824_0020
Revises: 20260824_0019
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20260824_0020"
down_revision = "20260824_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("origin", sa.String(20), server_default="MANUAL", nullable=False))
    op.add_column("tasks", sa.Column("source_suggestion_id", sa.BigInteger(), nullable=True))
    op.create_check_constraint("ck_task_origin", "tasks", "origin IN ('MANUAL', 'AI_APPROVED')")
    op.create_table(
        "task_activity_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("task_title", sa.String(300), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_task_activity_project_created", "task_activity_logs", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_task_activity_project_created", table_name="task_activity_logs")
    op.drop_table("task_activity_logs")
    op.drop_constraint("ck_task_origin", "tasks", type_="check")
    op.drop_column("tasks", "source_suggestion_id")
    op.drop_column("tasks", "origin")
