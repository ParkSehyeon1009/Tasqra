"""긴 분석의 진행 상태. 성공 결과와 완료 상태는 같은 트랜잭션에 저장한다."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','PARTIAL','FAILED')", name="ck_analysis_job_status"),
        Index("ix_analysis_job_document", "document_id", "created_at"),
        Index("uq_analysis_job_active", "document_id", unique=True,
              postgresql_where=text("status IN ('PENDING','RUNNING')")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"))
    document_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"))
    source_text_revision: Mapped[int] = mapped_column(Integer)
    source_text_hash: Mapped[str] = mapped_column(String(64))
    analyzer_types: Mapped[list] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    stage: Mapped[str] = mapped_column(String(160), default="대기 중")
    completed_units: Mapped[int] = mapped_column(Integer, default=0)
    total_units: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(String(300))
    analysis_ids: Mapped[list] = mapped_column(JSONB, default=list)
    analyzer_errors: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
