# =============================================================================
# 이 파일의 책임: 문서에서 뽑은 "결정사항" 한 건을 엔티티로 정의한다.
#   회의록의 "이관 대상은 인사시스템과 회계시스템 두 곳으로 한정한다" 같은 한 줄이
#   이 테이블의 한 행이다. 리비전 0007 이 만든 decisions 에 대응한다.
#
#   **테이블은 이미 있다. 이 파일은 매핑만 더한다.** 마이그레이션이 필요 없다.
#   지금까지 ORM 모델이 없어서 파이썬 코드가 이 테이블을 다룰 수 없었고, 그래서
#   대시보드가 결정사항을 세지 못하고 산출물도 못 만들었다.
#
# 다른 파일과의 관계
#   document.py    Document(1) : Decision(N) · Analysis(1) : Decision(N)
#   amount.py      AI 제안 승인 컬럼이 같은 모양이다 (아래 주석)
#   models/__init__.py 에서 import 되어야 Base.metadata 에 등록된다
#   이 모델이 풀어 주는 것 — 결정사항 대장(DLV-003-1) · 다음 회의 안건(DLV-003-2) ·
#   생성 대상 미리보기(DLV-001-2) · 대시보드 승인 대기 집계
#
# Spring 비교: JPA @Entity + @Table(indexes=..., check=...) 다.
#   Flyway 가 만든 테이블에 @Entity 만 붙이는 상황과 같다(ddl-auto=none).
#   자기 참조 FK(superseded_by)는 @ManyToOne(targetEntity=Decision.class) 이다.
#
# ⚠ status 와 decision 은 다른 것이다 — 섞으면 안 된다
#   리비전 0007 주석이 명시한다.
#     status    결정 **자체**의 상태. DECIDED / PENDING / REVERSED
#     decision  **AI 제안**의 승인 여부. PENDING / APPROVED / EDITED / REJECTED
#   즉 "사람이 승인한 제안(decision=APPROVED)" 이지만 "아직 결론이 안 난
#   안건(status=PENDING)" 일 수 있다. 둘 다 PENDING 값을 가져서 헷갈리기 쉽다.
#
#   다음 회의 안건(DLV-003-2)이 모으는 것은 **status='PENDING'** 이다.
#   0007 주석: "status='PENDING' 인 항목이 그대로 다음 회의 안건이 된다."
#
# ⚠ AI 제안 공통 컬럼을 믹스인으로 빼지 않았다
#   amount_items · decisions · schedule_items 가 같은 여섯 컬럼을 갖지만,
#   models/amount.py 가 이미 자체 정의를 갖고 있다. 지금 믹스인으로 모으면
#   **동작하는 amount.py 를 함께 고쳐야 하고** 그것은 이번 작업 범위가 아니다.
#   SQLAlchemy 선언적 매핑에서 딕셔너리를 펼치면 타입 검사기가 필드를 못 보는
#   문제도 있다. 값·제약이 갈리지 않게 **리비전 0007 을 유일한 근거로 삼는다.**
# =============================================================================

from datetime import date, datetime
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
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

__all__ = ["Decision"]

# 리비전 0007 의 DECISION_STATUS · SUGGESTION_DECISION 과 같은 값이다.
# enum 을 import 하지 않는 이유는 amount.py 와 같다 — 값 목록이 DB 의 CHECK
# 제약으로 굳어 있어서, 여기서 문자열로 두어야 "DB 와 맞춰야 하는 값" 임이 드러난다.
_STATUS = ("DECIDED", "PENDING", "REVERSED")
_DECISION = ("PENDING", "APPROVED", "EDITED", "REJECTED")


def _in_check(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Decision(Base):
    """결정사항 한 건. 문서에 적힌 결정을 그대로 담는다."""

    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(_in_check("status", _STATUS), name="ck_decision_status"),
        CheckConstraint(_in_check("decision", _DECISION), name="ck_decision_decision"),
        # 리비전 0007 이 만든 인덱스 넷. 이름과 컬럼 순서를 그대로 맞춘다 —
        # 다르면 Alembic autogenerate 가 지우고 다시 만드는 마이그레이션을 낸다.
        Index("ix_decision_project", "project_id", "decided_on"),
        Index("ix_decision_status", "project_id", "status"),
        Index("ix_decision_doc", "document_id"),
        # 미결 안건만 담는 부분 인덱스. 다음 회의 안건(DLV-003-2)이 이걸 쓴다.
        Index("ix_decision_open", "project_id", "created_at",
              postgresql_where=text("status = 'PENDING'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 프로젝트 스코프. 문서가 지워져도(document_id SET NULL) 결정은 프로젝트에
    # 남아야 하므로 project_id 를 따로 들고 있다.
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 출처 문서. 지워지면 NULL 이 된다 — 결정 자체는 남는다.
    document_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="SET NULL")
    )
    # 어느 분석 실행에서 나왔는지. 재분석하면 analyses 에 새 행이 쌓인다.
    analysis_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("analyses.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    evidence_text: Mapped[str | None] = mapped_column(Text)

    # 결정 **자체**의 상태다. AI 제안 승인 여부(decision)와 다르다 — 머리말 참고.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="DECIDED"
    )
    # 뒤집힌 결정 추적. 앞 결정을 REVERSED 로 두고 이 컬럼이 뒤 결정을 가리킨다.
    # 결정을 지우지 않는 이유 — "왜 바뀌었는지" 가 인수인계에서 가장 필요한 정보다.
    superseded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("decisions.id", ondelete="SET NULL")
    )
    decided_on: Mapped[date | None] = mapped_column(Date)

    # --- AI 제안 공통 컬럼 (amount_items · schedule_items 와 같은 모양) -------
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    # 근거는 페이지·좌표가 아니라 서술이다. 분석기가 텍스트만 받아 페이지를 모른다.
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING"
    )
    decided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # documents.ocr_revision 보다 작으면 오래된 제안이다(STALE_SUGGESTION).
    source_text_revision: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("Document", foreign_keys=[document_id])
    # 자기 참조. remote_side 로 "이쪽이 가리키는 쪽" 을 알려 준다 — 없으면
    # SQLAlchemy 가 방향을 정하지 못한다.
    superseded = relationship(
        "Decision", remote_side=[id], foreign_keys=[superseded_by]
    )

    @property
    def is_open(self) -> bool:
        """다음 회의 안건 대상인가 (DLV-003-2)."""
        return self.status == "PENDING"

    @property
    def is_pending_approval(self) -> bool:
        """AI 제안이 아직 승인되지 않았는가. is_open 과 다른 것이다."""
        return self.decision == "PENDING"
