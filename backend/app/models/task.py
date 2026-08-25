from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('TODO', 'IN_PROGRESS', 'DONE')", name="ck_task_status"),
        CheckConstraint("type IN ('DEVELOPMENT', 'DESIGN', 'INFRA', 'DOCUMENT', 'OTHER')", name="ck_task_type"),
        CheckConstraint("origin IN ('MANUAL', 'AI_APPROVED')", name="ck_task_origin"),
        Index("ix_task_project_status", "project_id", "status"),
        Index("ix_task_project_due", "project_id", "due_on"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="OTHER")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="TODO")
    assignee_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    due_on: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="MANUAL")
    # ⚠ 지금 이 컬럼에는 **amount_items.id** 가 들어간다 (금액 불일치 태스크 제안,
    #   AMT-004-3). 원래는 「제안 테이블의 id」 자리인데 그 테이블이 아직 없어서
    #   빌려 쓰고 있다.
    #
    #   빌려도 안전한 이유: 그때까지 이 컬럼은 전부 NULL 이었다(POST /tasks 가 값을
    #   넘기지 않았다). 그래서 들어가는 값이 한 종류뿐이고, 나중에 갈라놓을 때 어느
    #   행이 무엇인지 확실하다.
    #
    #   **task_suggestions 테이블을 만드는 리비전에서 반드시 갈라야 한다.**
    #     ① tasks 에 source_amount_item_id 추가 (FK → amount_items.id)
    #     ② UPDATE tasks SET source_amount_item_id = source_suggestion_id,
    #                        source_suggestion_id = NULL
    #        WHERE source_suggestion_id IS NOT NULL      ← 값이 한 종류라 안전
    #     ③ source_suggestion_id 에 FK → task_suggestions.id 추가
    #
    #   갈라야 하는 이유는 **한 컬럼이 두 테이블을 가리키면 FK 를 걸 수 없다**는
    #   것이다. FK 가 없으면 제안이 지워져도 태스크가 없는 id 를 가리킨 채 남고,
    #   에러 없이 추적만 끊긴다.
    source_suggestion_id: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    assignee = relationship("User", foreign_keys=[assignee_id])
    creator = relationship("User", foreign_keys=[created_by])


class TaskActivityLog(Base):
    __tablename__ = "task_activity_logs"
    __table_args__ = (Index("ix_task_activity_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tasks.id", ondelete="SET NULL"))
    task_title: Mapped[str] = mapped_column(String(300), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    actor = relationship("User", foreign_keys=[actor_id])
