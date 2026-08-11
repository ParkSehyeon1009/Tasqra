"""분석 산물(금액·결정·일정)과 산출물 테이블 추가

이 파일의 책임: 0006(ocr_review) 위에 4개 테이블을 얹는다.
  amount_items · decisions · schedule_items · deliverables
  기존 테이블에 컬럼을 추가하지 않는다(add_column 0건). 0006 으로 downgrade
  하면 정확히 이전 상태로 돌아간다.
다른 파일과의 관계: 0006 이 만든 OCR 검수 테이블(document_pages · ocr_elements
  · ocr_element_revisions)을 참조하지 않는다. analyses · documents · projects
  · users 만 참조하므로 OCR 검수 작업과 독립적으로 적용된다.
Spring 비교: Flyway V7__analysis_artifacts.sql 에 해당한다. Alembic 은 SQL
  대신 Python 으로 쓰므로 값 목록과 공통 컬럼을 함수로 뽑아 재사용한다.

이 파일이 왜 다시 만들어졌나
  앞서 20260811_0006_schema_expand 로 8개 테이블을 올렸는데, ocr-review
  브랜치가 같은 번호로 document_pages · ocr_elements · ocr_element_revisions
  를 다른 컬럼으로 정의했다. 그 3개는 원래 최재정님 OCR-DB 설계안에서 온
  것이고 화면 구현까지 되어 있으므로 그쪽 정의를 정본으로 삼는다.
  겹치지 않는 4개만 남겨 번호를 0007 로 올렸다.

ocr_groups 는 이번에 넣지 않았다
  단락 묶음을 별도 테이블로 두려 했으나, ocr_elements 에 group_id 가 필요해
  0006 의 테이블을 고쳐야 한다. 0006 은 element_type 컬럼으로 같은 목적을
  달성하고 있으므로 협의 후 별도 리비전으로 다룬다.

ENUM 대신 String + CHECK 를 쓰는 이유
  값이 바뀔 때 ALTER TYPE 이 필요 없다. CHECK 는 제약만 바꾸면 된다.
  Alembic autogenerate 도 ENUM 변경을 잘 잡지 못한다. 0001 부터 이어온 규칙이다.

Revision ID: 20260811_0007
Revises: 20260811_0006
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260811_0007"
down_revision = "20260811_0006"
branch_labels = None
depends_on = None


# ── 값 목록 ──────────────────────────────────────────────────────────────────
# 문자열을 두 번 적지 않도록 상수로 뽑는다. CHECK 문구와 오타가 어긋나는 것을 막는다.
SUGGESTION_DECISION = ("PENDING", "APPROVED", "EDITED", "REJECTED")
DECISION_STATUS = ("DECIDED", "PENDING", "REVERSED")
SCHEDULE_KIND = ("MILESTONE", "DEADLINE", "MEETING", "PERIOD")
DELIVERABLE_KIND = ("WEEKLY_REPORT", "DECISION_LOG", "MEETING_AGENDA",
                    "PROJECT_STATUS")
DELIVERABLE_FORMAT = ("XLSX", "HTML", "MD")


def in_check(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    joined = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} IN ({joined})", name=name)


def nullable_in_check(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    joined = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} IS NULL OR {column} IN ({joined})", name=name)


def timestamps() -> list[sa.Column]:
    """0001 과 같은 헬퍼. 두 컬럼을 항상 같은 모양으로 만든다."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def suggestion_columns() -> list[sa.Column]:
    """AI 제안이 공유하는 컬럼.

    근거는 페이지·좌표가 아니라 reason(판단 근거 서술)과 source_quote(원문 인용)
    으로 표시한다. 분석기 규격이 텍스트만 받아 페이지를 알 수 없기 때문이다.
    페이지 번호를 근거에 넣는 안은 별도 안건으로 남겨두었다.
    """
    return [
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(20), server_default="PENDING",
                  nullable=False),
        sa.Column("decided_by", sa.BigInteger(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        # 이 값이 documents.ocr_revision 보다 작으면 오래된 제안이다.
        sa.Column("source_text_revision", sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    # ═════════════════════════════════════════════════════════════════════
    # 1. 분석 산물   금액 · 결정 · 일정
    #
    # 항목마다 컬럼이 같아 테이블로 둔다. JSONB 배열 안에 넣으면 승인·거부
    # 상태를 원소 단위로 관리할 수 없고 기간 집계 쿼리도 성립하지 않는다.
    # ═════════════════════════════════════════════════════════════════════
    op.create_table(
        "amount_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", sa.BigInteger(),
                  sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_name", sa.String(300), nullable=False),
        # 문서에 없으면 NULL 이다. LLM 이 채우지 않는다.
        # 추계(없는 금액 만들기)를 하지 않고 집계만 하므로 단가 마스터가 없다.
        sa.Column("quantity", sa.Numeric(18, 4)),
        sa.Column("unit", sa.String(30)),
        sa.Column("amount", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(3), server_default="KRW", nullable=False),
        sa.Column("period_from", sa.Date()),
        sa.Column("period_to", sa.Date()),
        # 표시용 원문 인용. 클릭 이동은 범위 밖이다.
        sa.Column("source_quote", sa.String(1000)),
        *suggestion_columns(),
        *timestamps(),
        in_check("decision", SUGGESTION_DECISION, "ck_amount_decision"),
        sa.CheckConstraint(
            "period_from IS NULL OR period_to IS NULL OR period_from <= period_to",
            name="ck_amount_period"),
    )
    op.create_index("ix_amount_doc", "amount_items", ["document_id"])
    op.create_index("ix_amount_analysis", "amount_items", ["analysis_id"])
    op.create_index("ix_amount_pending", "amount_items", ["document_id"],
                    postgresql_where=sa.text("decision = 'PENDING'"))

    op.create_table(
        "decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("analysis_id", sa.BigInteger(),
                  sa.ForeignKey("analyses.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", sa.Text()),
        # status 는 결정 자체의 상태, decision 은 AI 제안의 승인 여부다.
        # status='PENDING' 인 항목이 그대로 다음 회의 안건이 된다.
        sa.Column("status", sa.String(20), server_default="DECIDED", nullable=False),
        # 뒤집힌 결정 추적. 앞 결정을 REVERSED 로 두고 뒤 결정을 가리킨다.
        sa.Column("superseded_by", sa.BigInteger(),
                  sa.ForeignKey("decisions.id", ondelete="SET NULL")),
        sa.Column("decided_on", sa.Date()),
        *suggestion_columns(),
        *timestamps(),
        in_check("status", DECISION_STATUS, "ck_decision_status"),
        in_check("decision", SUGGESTION_DECISION, "ck_decision_decision"),
    )
    op.create_index("ix_decision_project", "decisions", ["project_id", "decided_on"])
    op.create_index("ix_decision_status", "decisions", ["project_id", "status"])
    op.create_index("ix_decision_doc", "decisions", ["document_id"])
    op.create_index("ix_decision_open", "decisions", ["project_id", "created_at"],
                    postgresql_where=sa.text("status = 'PENDING'"))

    op.create_table(
        "schedule_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.BigInteger(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("analysis_id", sa.BigInteger(),
                  sa.ForeignKey("analyses.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("starts_on", sa.Date()),
        sa.Column("ends_on", sa.Date()),
        *suggestion_columns(),
        *timestamps(),
        in_check("kind", SCHEDULE_KIND, "ck_schedule_kind"),
        in_check("decision", SUGGESTION_DECISION, "ck_schedule_decision"),
        sa.CheckConstraint(
            "starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on",
            name="ck_schedule_dates"),
    )
    op.create_index("ix_schedule_project", "schedule_items",
                    ["project_id", "starts_on"])
    op.create_index("ix_schedule_due", "schedule_items", ["project_id", "ends_on"])
    op.create_index("ix_schedule_doc", "schedule_items", ["document_id"])

    # ═════════════════════════════════════════════════════════════════════
    # 2. 산출물   문서를 넣으면 문서가 나온다
    # ═════════════════════════════════════════════════════════════════════
    op.create_table(
        "deliverables",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        # 기본값을 두지 않는다. 미지정이면 API 가 FORMAT_REQUIRED 를 낸다.
        sa.Column("format", sa.String(10), nullable=False),
        # 주간 보고서만 기간이 필요하다.
        # 결정사항 대장·현황 한 장은 전체 누적이라 NULL 이다.
        sa.Column("period_from", sa.Date()),
        sa.Column("period_to", sa.Date()),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("file_size", sa.BigInteger()),
        # 생성 시점 스냅샷. 현재 개수와 비교해 '다시 만들기' 를 띄운다.
        sa.Column("source_counts_json", postgresql.JSONB(), nullable=False),
        sa.Column("generated_by", sa.BigInteger(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("generated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        in_check("kind", DELIVERABLE_KIND, "ck_deliverable_kind"),
        in_check("format", DELIVERABLE_FORMAT, "ck_deliverable_format"),
        sa.CheckConstraint(
            "kind <> 'WEEKLY_REPORT'"
            " OR (period_from IS NOT NULL AND period_to IS NOT NULL)",
            name="ck_deliverable_period_required"),
        sa.CheckConstraint(
            "period_from IS NULL OR period_to IS NULL OR period_from <= period_to",
            name="ck_deliverable_period_order"),
    )
    op.create_index("ix_deliverable_recent", "deliverables",
                    ["project_id", "generated_at"])
    op.create_index("ix_deliverable_period", "deliverables",
                    ["project_id", "kind", "period_from", "period_to"])


def downgrade() -> None:
    # 생성의 역순. 참조하는 쪽을 먼저 지운다.
    op.drop_table("deliverables")
    op.drop_table("schedule_items")
    op.drop_table("decisions")
    op.drop_table("amount_items")
