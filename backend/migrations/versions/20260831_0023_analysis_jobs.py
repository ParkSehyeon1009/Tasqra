"""백그라운드 AI 분석 상태와 중복 작업 방지.

Revision ID: 20260831_0023
Revises: 20260825_0022
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260831_0023"
down_revision = "20260825_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("analysis_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_text_revision", sa.Integer(), nullable=False),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
        sa.Column("analyzer_types", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("stage", sa.String(160), nullable=False),
        sa.Column("completed_units", sa.Integer(), nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("error_message", sa.String(300)),
        sa.Column("analysis_ids", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED')", name="ck_analysis_job_status"),
    )
    op.create_index("ix_analysis_job_document", "analysis_jobs", ["document_id", "created_at"])
    op.create_index("uq_analysis_job_active", "analysis_jobs", ["document_id"], unique=True,
                    postgresql_where=sa.text("status IN ('PENDING','RUNNING')"))


def downgrade():
    op.drop_table("analysis_jobs")
