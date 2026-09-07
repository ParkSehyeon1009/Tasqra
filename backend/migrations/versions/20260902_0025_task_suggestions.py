"""AI 액션 태스크 제안과 출처 연결 분리.

Revision ID: 20260902_0025
Revises: 20260902_0024
"""
import sqlalchemy as sa
from alembic import op

revision = "20260902_0025"
down_revision = "20260902_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "task_suggestions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("analysis_id", sa.BigInteger(), sa.ForeignKey("analyses.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("due_on", sa.Date()),
        sa.Column("actor", sa.String(160)),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("decided_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("source_text_revision", sa.Integer(), nullable=False),
        sa.Column("created_task_id", sa.BigInteger(), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('PENDING','APPROVED','EDITED','REJECTED')", name="ck_task_suggestion_decision"),
    )
    op.create_index("ix_task_suggestion_project", "task_suggestions", ["project_id", "decision"])
    op.create_index("ix_task_suggestion_document", "task_suggestions", ["document_id"])
    op.add_column("tasks", sa.Column("source_amount_item_id", sa.BigInteger(), nullable=True))
    op.execute("UPDATE tasks SET source_amount_item_id=source_suggestion_id, source_suggestion_id=NULL WHERE source_suggestion_id IS NOT NULL")
    op.create_foreign_key("fk_tasks_source_amount_item", "tasks", "amount_items", ["source_amount_item_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_tasks_source_suggestion", "tasks", "task_suggestions", ["source_suggestion_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint("uq_tasks_source_suggestion", "tasks", ["source_suggestion_id"])


def downgrade():
    op.drop_constraint("uq_tasks_source_suggestion", "tasks", type_="unique")
    op.drop_constraint("fk_tasks_source_suggestion", "tasks", type_="foreignkey")
    op.drop_constraint("fk_tasks_source_amount_item", "tasks", type_="foreignkey")
    op.execute("UPDATE tasks SET source_suggestion_id=source_amount_item_id WHERE source_amount_item_id IS NOT NULL")
    op.drop_column("tasks", "source_amount_item_id")
    op.drop_table("task_suggestions")
