# =============================================================================
# 이 파일의 책임: 문서에서 뽑은 "일정·기한" 한 건을 엔티티로 정의한다.
#   회의록의 "산출물 제출 시점을 착수 후 4주로 한다" 나 공고문의 "계약 기간
#   12개월" 같은 한 줄이 이 테이블의 한 행이다. 리비전 0007 이 만든
#   schedule_items 에 대응한다.
#
#   **테이블은 이미 있다. 이 파일은 매핑만 더한다.** 마이그레이션이 필요 없다.
#
# 다른 파일과의 관계
#   document.py    Document(1) : ScheduleItem(N) · Analysis(1) : ScheduleItem(N)
#   decision.py    AI 제안 승인 컬럼이 같은 모양이다
#   models/__init__.py 에서 import 되어야 Base.metadata 에 등록된다
#   이 모델이 풀어 주는 것 — 생성 대상 미리보기의 "다가오는 기한"(DLV-001-2) ·
#   주간 보고서의 기한 절(DLV-002-1) · 프로젝트 현황 한 장(DLV-002-2)
#
# Spring 비교: JPA @Entity 다. kind 를 @Enumerated 로 두지 않고 String + CHECK 로
#   두는 것은 리비전 0007 의 판단을 따른 것이다 — 값이 바뀔 때 ALTER TYPE 이
#   필요 없고 Alembic autogenerate 가 ENUM 변경을 잘 잡지 못한다.
#
# ⚠ kind 네 값의 뜻이 서로 다르다 — 날짜 컬럼의 쓰임이 갈린다
#     MILESTONE  한 시점. starts_on 만 의미가 있다
#     DEADLINE   기한. ends_on 만 의미가 있다
#     MEETING    한 시점. starts_on 만 의미가 있다
#     PERIOD     구간. starts_on ~ ends_on 둘 다 필요하다
#   **DB 는 둘 다 nullable 로 두었다.** 문서에 없으면 NULL 이어야 하고, LLM 이
#   만들어 채우면 안 되기 때문이다. 그래서 "DEADLINE 인데 ends_on 이 NULL" 인
#   행이 있을 수 있다 — 화면·보고서가 그 경우를 처리해야 한다.
#   CHECK 는 순서만 본다(starts_on <= ends_on).
# =============================================================================

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

__all__ = ["ScheduleItem"]

# 리비전 0007 의 SCHEDULE_KIND · SUGGESTION_DECISION 과 같은 값이다.
_KIND = ("MILESTONE", "DEADLINE", "MEETING", "PERIOD")
_DECISION = ("PENDING", "APPROVED", "EDITED", "REJECTED")


def _in_check(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class ScheduleItem(Base):
    """일정·기한 한 건. 문서에 적힌 날짜를 그대로 담는다."""

    __tablename__ = "schedule_items"
    __table_args__ = (
        CheckConstraint(_in_check("kind", _KIND), name="ck_schedule_kind"),
        CheckConstraint(_in_check("decision", _DECISION), name="ck_schedule_decision"),
        CheckConstraint(
            "starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on",
            name="ck_schedule_dates",
        ),
        # 리비전 0007 의 인덱스 셋. 이름·컬럼 순서를 그대로 맞춘다.
        Index("ix_schedule_project", "project_id", "starts_on"),
        # "다가오는 기한" 조회용. ends_on 으로 정렬한다.
        Index("ix_schedule_due", "project_id", "ends_on"),
        Index("ix_schedule_doc", "document_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="SET NULL")
    )
    analysis_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("analyses.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)
    # MILESTONE · DEADLINE · MEETING · PERIOD. 머리말의 날짜 쓰임 표를 볼 것.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # 문서에 없으면 NULL 이다. 만들어 채우지 않는다.
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    starts_time: Mapped[time | None] = mapped_column(Time)
    ends_time: Mapped[time | None] = mapped_column(Time)
    relative_expression: Mapped[str | None] = mapped_column(String(300))
    temporal_type: Mapped[str | None] = mapped_column(String(40))
    precision: Mapped[str | None] = mapped_column(String(20))
    anchor_event: Mapped[str | None] = mapped_column(String(120))
    calendar_rule: Mapped[str | None] = mapped_column(String(30))
    condition: Mapped[str | None] = mapped_column(Text)
    tentative: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    # --- AI 제안 공통 컬럼 (amount_items · decisions 와 같은 모양) ------------
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING"
    )
    decided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_text_revision: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("Document", foreign_keys=[document_id])

    @property
    def due_on(self) -> date | None:
        """이 항목의 "기한" 으로 볼 날짜.

        kind 마다 어느 컬럼이 기한인지 다르다. 화면·보고서가 매번 분기하지 않게
        한 곳에 둔다.

        MILESTONE · MEETING 은 한 시점이라 starts_on 이 곧 기한이다.
        DEADLINE 은 ends_on 이 기한이다. PERIOD 는 끝나는 날을 기한으로 본다.
        둘 다 NULL 일 수 있다 — 문서에 날짜가 없었던 경우다.
        """
        if self.kind in ("MILESTONE", "MEETING"):
            return self.starts_on
        return self.ends_on or self.starts_on
