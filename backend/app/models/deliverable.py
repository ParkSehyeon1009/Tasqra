# =============================================================================
# 이 파일의 책임: 만들어 낸 산출물 파일 한 건을 엔티티로 정의한다.
#   "8월 11~17일 주간 보고서 XLSX" 한 건이 이 테이블의 한 행이다.
#   리비전 0007 이 만든 deliverables 에 대응한다.
#
#   **테이블은 이미 있다. 이 파일은 매핑만 더한다.** 마이그레이션이 필요 없다.
#
#   위 세 모델(amount·decision·schedule)과 성격이 다르다 — 이건 **AI 제안이
#   아니다.** 우리가 만든 결과물이므로 승인 컬럼(decision·reason 등)이 없다.
#
# 다른 파일과의 관계
#   decision.py · schedule.py · amount.py 가 이 산출물의 재료다
#   models/__init__.py 에서 import 되어야 Base.metadata 에 등록된다
#   이 모델이 풀어 주는 것 — 생성 이력·다운로드(DLV-003-3) ·
#   갱신 필요 판정(DLV-003-4)
#
# Spring 비교: JPA @Entity 다. source_counts_json 은 JSONB 컬럼이라
#   @Type(JsonType.class) 나 @JdbcTypeCode(SqlTypes.JSON) 을 붙인 필드에 해당한다.
#
# ⚠ source_counts_json 이 이 테이블의 핵심이다
#   **생성 시점의 재료 개수를 찍어 둔 스냅샷**이다. 지금 개수와 비교해서
#   "다시 만들기" 를 띄운다(DLV-003-4 완료 판정: "생성 후 대상이 추가되면 갱신
#   필요 표시가 뜬다").
#
#       생성 시   {"documents": 12, "tasks": 8, "decisions": 5, ...}
#       지금      {"documents": 15, "tasks": 8, "decisions": 6, ...}
#       -> 문서 3건·결정 1건이 늘었다 -> 갱신 필요
#
#   파일을 다시 만들어 비교하는 방식이 아니라 **개수만 비교**하는 이유는 LLM
#   호출 비용이다. 개수가 같으면 내용도 같다고 본다 — 문서가 수정만 된 경우는
#   못 잡지만, 그건 원천 데이터의 갱신 시각을 따로 봐야 하는 별도 문제다.
#
# ⚠ kind 에 따라 기간이 필요한지 갈린다 (DB CHECK 가 강제한다)
#     WEEKLY_REPORT   period_from · period_to **필수** (ck_deliverable_period_required)
#     DECISION_LOG    전체 누적이라 NULL
#     MEETING_AGENDA  미결 항목 전체라 NULL
#     PROJECT_STATUS  현재 상태라 NULL
# =============================================================================

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

__all__ = ["Deliverable"]

# 리비전 0007 의 DELIVERABLE_KIND · DELIVERABLE_FORMAT 과 같은 값이다.
_KIND = ("WEEKLY_REPORT", "DECISION_LOG", "MEETING_AGENDA", "PROJECT_STATUS")
_FORMAT = ("XLSX", "HTML", "MD")

# 기간이 필수인 유형. DB CHECK 와 같은 판단을 코드에서도 쓸 수 있게 둔다.
PERIOD_REQUIRED_KINDS = ("WEEKLY_REPORT",)


def _in_check(column: str, values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({joined})"


class Deliverable(Base):
    """만들어 낸 산출물 파일 한 건."""

    __tablename__ = "deliverables"
    __table_args__ = (
        CheckConstraint(_in_check("kind", _KIND), name="ck_deliverable_kind"),
        CheckConstraint(_in_check("format", _FORMAT), name="ck_deliverable_format"),
        # 주간 보고서만 기간이 필수다.
        CheckConstraint(
            "kind <> 'WEEKLY_REPORT'"
            " OR (period_from IS NOT NULL AND period_to IS NOT NULL)",
            name="ck_deliverable_period_required",
        ),
        CheckConstraint(
            "period_from IS NULL OR period_to IS NULL OR period_from <= period_to",
            name="ck_deliverable_period_order",
        ),
        # 리비전 0007 의 인덱스 둘. 이름·컬럼 순서를 그대로 맞춘다.
        # 최근 생성 목록 조회용.
        Index("ix_deliverable_recent", "project_id", "generated_at"),
        # "같은 유형·같은 기간을 이미 만들었나" 조회용.
        Index("ix_deliverable_period", "project_id", "kind", "period_from", "period_to"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # 기본값을 두지 않는다. 미지정이면 API 가 FORMAT_REQUIRED 를 낸다.
    format: Mapped[str] = mapped_column(String(10), nullable=False)

    # 주간 보고서만 필요하다. 나머지는 전체 누적이라 NULL 이다.
    period_from: Mapped[date | None] = mapped_column(Date)
    period_to: Mapped[date | None] = mapped_column(Date)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)

    # 생성 시점 재료 개수 스냅샷. 머리말 참고. 갱신 필요 판정의 근거다.
    source_counts_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    generated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project = relationship("Project", foreign_keys=[project_id])

    @property
    def needs_period(self) -> bool:
        """이 유형이 기간을 요구하는가. DB CHECK 와 같은 판단이다."""
        return self.kind in PERIOD_REQUIRED_KINDS

    def stale_against(self, current: dict[str, int]) -> dict[str, int]:
        """지금 개수와 비교해 **늘어난 만큼**을 돌려준다 (DLV-003-4).

        늘어난 항목만 담는다. 빈 딕셔너리면 갱신이 필요 없다.

        줄어든 경우는 담지 않는다 — 문서를 지웠다고 보고서를 다시 만들 이유가
        없고, "갱신 필요" 를 띄우면 사용자가 왜인지 알 수 없다.

        생성 시점에 없던 열쇠가 지금 생겼으면 그 값 전부가 늘어난 것으로 본다
        (재료 종류가 나중에 추가된 경우).
        """
        snapshot = self.source_counts_json or {}
        grown: dict[str, int] = {}
        for key, now in current.items():
            before = int(snapshot.get(key, 0) or 0)
            if now > before:
                grown[key] = now - before
        return grown
