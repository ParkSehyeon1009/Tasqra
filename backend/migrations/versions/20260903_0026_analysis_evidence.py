"""분석 결과의 원문 근거와 액션 태스크 중복 지문 추가.

Revision ID: 20260903_0026
Revises: 20260902_0025
"""
import sqlalchemy as sa
from alembic import op

revision = "20260903_0026"
down_revision = "20260902_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("task_suggestions", sa.Column("evidence_fingerprint", sa.String(64)))
    op.execute("UPDATE task_suggestions SET evidence_fingerprint = md5(regexp_replace(lower(evidence_text), '[[:space:]]+', '', 'g'))")
    op.create_index("ix_task_suggestion_evidence", "task_suggestions",
                    ["project_id", "document_id", "evidence_fingerprint"])
    op.add_column("decisions", sa.Column("evidence_text", sa.Text()))
    op.add_column("schedule_items", sa.Column("evidence_text", sa.Text()))


def downgrade():
    op.drop_column("schedule_items", "evidence_text")
    op.drop_column("decisions", "evidence_text")
    op.drop_index("ix_task_suggestion_evidence", table_name="task_suggestions")
    op.drop_column("task_suggestions", "evidence_fingerprint")
