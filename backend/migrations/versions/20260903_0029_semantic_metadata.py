"""Preserve semantic metadata for tasks, decisions, and schedules.

Revision ID: 20260903_0029
Revises: 20260903_0028
"""
import sqlalchemy as sa
from alembic import op

revision = "20260903_0029"
down_revision = "20260903_0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("package_key", sa.String(500)))
    op.add_column("documents", sa.Column("package_role", sa.String(40)))
    op.create_index("ix_doc_package", "documents", ["project_id", "package_key"])
    op.add_column("task_suggestions", sa.Column("actor_scope", sa.String(30)))
    op.add_column("task_suggestions", sa.Column("statement_type", sa.String(40), nullable=False, server_default="OBLIGATION"))
    op.add_column("task_suggestions", sa.Column("task_kind", sa.String(40)))
    op.add_column("task_suggestions", sa.Column("modality", sa.String(30)))
    op.add_column("task_suggestions", sa.Column("recipient", sa.String(160)))
    op.add_column("task_suggestions", sa.Column("relative_expression", sa.String(300)))
    op.add_column("task_suggestions", sa.Column("condition", sa.Text()))
    op.add_column("decisions", sa.Column("decision_type", sa.String(40)))
    op.add_column("schedule_items", sa.Column("temporal_type", sa.String(40)))
    op.add_column("schedule_items", sa.Column("precision", sa.String(20)))
    op.add_column("schedule_items", sa.Column("anchor_event", sa.String(120)))
    op.add_column("schedule_items", sa.Column("calendar_rule", sa.String(30)))
    op.add_column("schedule_items", sa.Column("condition", sa.Text()))
    op.add_column("schedule_items", sa.Column("tentative", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("schedule_items", "tentative")
    op.drop_column("schedule_items", "condition")
    op.drop_column("schedule_items", "calendar_rule")
    op.drop_column("schedule_items", "anchor_event")
    op.drop_column("schedule_items", "precision")
    op.drop_column("schedule_items", "temporal_type")
    op.drop_column("decisions", "decision_type")
    op.drop_column("task_suggestions", "condition")
    op.drop_column("task_suggestions", "relative_expression")
    op.drop_column("task_suggestions", "recipient")
    op.drop_column("task_suggestions", "modality")
    op.drop_column("task_suggestions", "task_kind")
    op.drop_column("task_suggestions", "statement_type")
    op.drop_column("task_suggestions", "actor_scope")
    op.drop_index("ix_doc_package", table_name="documents")
    op.drop_column("documents", "package_role")
    op.drop_column("documents", "package_key")
