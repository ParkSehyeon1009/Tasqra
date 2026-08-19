# =============================================================================
# 이 파일의 책임: 문서에서 추출한 금액 항목 한 줄을 엔티티로 정의한다.
#   산출내역서·계약서의 "항목명 · 수량 · 단위 · 단가 · 금액 · 원가구분" 한 행이
#   이 테이블의 한 행이다. 리비전 0007 이 만든 amount_items 에 대응하고,
#   리비전 0015 가 unit_price · category 를 더했다.
# 다른 파일과의 관계: document.py 의 Document(1) : AmountItem(N) 이고
#   Analysis(1) : AmountItem(N) 이다. schemas/amount.py 의 AmountItemOut 이 LLM
#   추출 계약이고, services/amount_normalizer.py 가 정규화한 뒤 스키마가 검증한
#   값이 이 테이블로 들어온다. services/amount_calculator.py 가 이 값을 읽어
#   수량x단가 검산(AMT-002-1)과 원가구분별 집계(AMT-002-2)를 한다.
#   models/__init__.py 에서 import 되어야 Base.metadata 에 등록된다.
# Spring 비교: JPA @Entity + @Table(indexes=..., check=...) 에 대응한다.
#   Mapped[Decimal | None] 은 @Column(precision=, scale=) 붙은 BigDecimal 필드와
#   같고, relationship() 은 @ManyToOne 이다. Numeric 을 쓰고 float 를 쓰지 않는
#   것은 JPA 에서 금액에 double 대신 BigDecimal 을 쓰는 것과 같은 이유다.
#
# !! 이 테이블은 "문서에서 읽은 값" 만 담는다. 추계값(우리가 산출한 추정치)을
#    여기 넣지 말 것.
#
#    not-null 컬럼이 전부 문서 출처를 전제한다 — document_id · analysis_id ·
#    source_text_revision · reason. 추계값에는 그것들이 없다. 억지로 넣으려면
#    네 컬럼을 nullable 로 되돌리고 "추출인지 추계인지" 구분 컬럼을 더한 뒤
#    기존 모든 쿼리에 그 필터를 붙여야 하는데, 한 곳이라도 빠뜨리면 추계값이
#    "문서에 적힌 금액" 으로 집계된다. 에러 없이 숫자만 틀리는 사고다.
#
#    더 근본적인 이유는 두 값의 신뢰 수준이 다르다는 것이다. "문서에
#    28,500,000 이라고 적혀 있다" 와 "과거 선례로 추정하면 28,500,000 쯤이다" 는
#    다른 주장이고, 섞으면 화면·보고서에서 구별이 사라진다. 조달 문서에서 그건
#    위험하다. 추계를 하게 되면 amount_estimates 같은 별도 테이블(프로젝트 단위)
#    로 간다. 그때 이 파일을 고칠 필요는 없다.
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

__all__ = ["AmountItem"]

# models/enums.py 의 AmountCategory · SuggestionDecision 과 같은 값이다.
# CHECK 문구를 만들 때만 쓴다. enum 을 직접 import 하지 않는 이유는 리비전
# 0015 와 같다 — 값 목록이 스키마 제약으로 굳어 있으므로 여기서도 문자열로 둔다.
_CATEGORY = (
    "DIRECT_LABOR", "EXPENSE", "OVERHEAD", "TECH_FEE",
    "MATERIAL", "SUBCONTRACT", "VAT", "OTHER",
)
_DECISION = ("PENDING", "APPROVED", "EDITED", "REJECTED")


def _in_check(column: str, values: tuple[str, ...], *, nullable: bool) -> str:
    joined = ", ".join(f"'{value}'" for value in values)
    if nullable:
        return f"{column} IS NULL OR {column} IN ({joined})"
    return f"{column} IN ({joined})"


class AmountItem(Base):
    """금액 항목 한 줄. 문서에 적힌 것을 그대로 담는다."""

    __tablename__ = "amount_items"
    __table_args__ = (
        CheckConstraint(_in_check("decision", _DECISION, nullable=False),
                        name="ck_amount_decision"),
        CheckConstraint(_in_check("category", _CATEGORY, nullable=True),
                        name="ck_amount_category"),
        CheckConstraint("unit_price IS NULL OR unit_price >= 0",
                        name="ck_amount_unit_price"),
        CheckConstraint(
            "period_from IS NULL OR period_to IS NULL OR period_from <= period_to",
            name="ck_amount_period"),
        Index("ix_amount_doc", "document_id"),
        Index("ix_amount_analysis", "analysis_id"),
        # 승인 대기 건수를 세는 조회용. 부분 인덱스라 PENDING 행만 담는다.
        Index("ix_amount_pending", "document_id",
              postgresql_where=text("decision = 'PENDING'")),
        # 원가구분별 집계(aggregate_by_category)가 이 순서로 조회한다. 리비전 0015.
        Index("ix_amount_category", "document_id", "category"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    # 어느 분석 실행에서 나온 항목인지. 재분석하면 analyses 에 새 행이 쌓이므로
    # (DOC-006-2) 이 값으로 "최신 분석의 금액" 과 과거 것을 구별한다.
    analysis_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False
    )

    item_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # 원가구분. 판별하지 못하면 NULL 이다 — OTHER 를 넣으면 "판별 못 했다" 와
    # "기타로 판별했다" 를 구별할 수 없다. 리비전 0015.
    category: Mapped[str | None] = mapped_column(String(20))

    # 아래 넷은 문서에 없으면 NULL 이다. LLM 이 만들어 채우지 않는다.
    # 제경비·기술료처럼 비율로 산정된 항목은 수량·단가가 원래 없다.
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(30))
    # 리비전 0015. amount_calculator.verify_line() 이 quantity 와 곱해 검산한다.
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    # 문서에 적힌 금액. 수량x단가와 어긋나도 이 값을 고치지 않는다 —
    # 코드가 고치면 문서의 오류가 숨어서 합계 대조가 무의미해진다.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="KRW"
    )

    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)
    # 표시용 원문 인용. 클릭해서 원문 위치로 가는 것은 별도 안건이다
    # (검색 쪽은 content_start·content_end 로 그것을 한다).
    source_quote: Mapped[str | None] = mapped_column(String(1000))

    # --- AI 제안 공통 컬럼 (decisions · schedule_items 와 같은 모양) ----------
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # 승인 전에는 어디에도 반영하지 않는다 (AMT-001-2). 사용자가 값을 고치면
    # EDITED 로 남는다 — 회사마다 산정식이 달라 우리 검산이 불일치로 나올 때의
    # 탈출구가 이것이다. 수식을 편집하게 하는 대신 값을 고치고 사실을 기록한다.
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="PENDING"
    )
    decided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 이 값이 documents.ocr_revision 보다 작으면 낡은 제안이다. 검수로 본문이
    # 바뀌면 금액도 다시 뽑아야 한다는 판정에 쓴다 (REV-004-5 와 같은 방식).
    source_text_revision: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # back_populates 를 쓰지 않는다. 반대편(Document · Analysis)에 컬렉션을
    # 더하려면 document.py 를 고쳐야 하는데, 지금 이 관계를 쓰는 코드가 없어서
    # 단방향으로 둔다. 필요해지면 그때 양쪽을 함께 연결한다.
    document = relationship("Document")
    analysis = relationship("Analysis")

    @property
    def is_pending(self) -> bool:
        """아직 사람이 승인·거절하지 않았는가."""
        return self.decision == "PENDING"

    @property
    def line_total(self) -> Decimal | None:
        """수량 x 단가. 둘 중 하나라도 없으면 None 이다.

        amount 와 비교하는 것은 services/amount_calculator.py 가 한다. 여기서는
        곱셈만 제공하고 판정하지 않는다 — 모델이 비즈니스 판단을 갖지 않게 한다.
        """
        if self.quantity is None or self.unit_price is None:
            return None
        return self.quantity * self.unit_price
