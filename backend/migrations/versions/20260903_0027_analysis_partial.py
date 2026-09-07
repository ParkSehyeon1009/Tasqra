"""분석기별 부분 성공 상태와 오류 기록.

Revision ID: 20260903_0027
Revises: 20260903_0026
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260903_0027"
down_revision = "20260903_0026"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_analysis_job_status", "analysis_jobs", type_="check")
    op.create_check_constraint("ck_analysis_job_status", "analysis_jobs",
        "status IN ('PENDING','RUNNING','COMPLETED','PARTIAL','FAILED')")
    op.add_column("analysis_jobs", sa.Column("analyzer_errors", JSONB(),
        nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade():
    op.execute("UPDATE analysis_jobs SET status='FAILED' WHERE status='PARTIAL'")
    op.drop_column("analysis_jobs", "analyzer_errors")
    op.drop_constraint("ck_analysis_job_status", "analysis_jobs", type_="check")
    op.create_check_constraint("ck_analysis_job_status", "analysis_jobs",
        "status IN ('PENDING','RUNNING','COMPLETED','FAILED')")
