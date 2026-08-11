"""OCR 검수 · 분석 산물 · 산출물 테이블 추가

이 파일의 책임: 0001(users·projects·project_members·documents·extracted_texts·
  analyses) · 0002(users.login_id) · 0003(project_invitations) 위에
  8개 테이블을 얹는다.
  앞선 세 리비전이 만든 것은 **하나도 건드리지 않는다.** 기존 테이블에
  컬럼을 추가하지도 않는다(add_column 0건). 테이블 8개 · 인덱스 18개 ·
  제약 11개의 이름이 기존과 겹치지 않는 것을 AST 로 대조해 확인했다.
다른 파일과의 관계: 최재정님 'OCR 결과 확인·사용자 수정 기능을 위한 DB 설계안'
  4·5절을 그대로 반영했다. 0001 의 규칙을 이어간다 — ENUM 타입을 만들지 않고
  String + CheckConstraint 로 값을 제한하고 timestamps() 로 시각 컬럼을 통일한다.
Spring 비교: Flyway V3__schema_expand.sql 에 해당한다. Alembic 은 SQL 대신
  Python 으로 쓰므로 값 목록과 공통 컬럼을 함수로 뽑아 재사용할 수 있다.

ENUM 대신 String + CHECK 를 쓰는 이유
  값이 바뀔 때 ALTER TYPE 이 필요 없다. document_type 이 6종에서 7종으로
  늘어난 것처럼 값은 계속 변하고, CHECK 는 제약만 바꾸면 된다.
  Alembic autogenerate 도 ENUM 변경을 잘 잡지 못한다.

이번에 넣지 않은 테이블 5개
  batch_jobs      일괄 업로드가 최재정님 파트로 확정되고 일정이 뒤로 밀렸다.
  batch_items     설계는 그분의 3모드 확장안에서 온 것이므로, 구현 시점에
                  본인 리비전으로 넣는 편이 낫다. 지금 만들면 컬럼을 고칠 때
                  ALTER 리비전을 하나 더 얹어야 한다.
                  documents.batch_item_id 도 같은 이유로 뺐다. 안 쓰는 FK
                  컬럼을 가장 바쁜 테이블에 미리 붙이지 않는다.
  action_items    제안 4종을 대칭으로 만들자는 제안이 합의 대기다.
                  tasks 의 출처 FK 이름을 바꿔야 해서 함께 결정해야 한다.
  tasks           박세현님이 작업 중이라 머지 충돌을 피한다.
  activity_logs   같은 이유.

배치 컬럼을 뺐어도 이 리비전은 독립적으로 적용된다. 8개 테이블 중 batch_items
를 참조하는 것이 하나도 없기 때문이다(FK 대상 8종 전수 확인).

Revision ID: 20260810_0004
Revises: 20260810_0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260810_0004"
down_revision = "20260810_0003"
branch_labels = None
depends_on = None


# ── 값 목록 ──────────────────────────────────────────────────────────────────
# 문자열을 두 번 적지 않도록 상수로 뽑는다. CHECK 문구와 오타가 어긋나는 것을 막는다.
DOCUMENT_TYPE = ("CONTRACT", "CONTRACT_CHANGE", "MEETING_NOTES", "REPORT",
                 "NOTICE", "MANUAL", "ETC")
OCR_SOURCE = ("OCR", "TEXT_LAYER", "MANUAL", "RE_OCR")
OCR_REVIEW_STATUS = ("UNREVIEWED", "REVIEWED", "REJECTED")
OCR_GROUP_TYPE = ("PARAGRAPH", "HEADING", "TABLE", "TABLE_ROW", "LIST",
                  "CAPTION", "FOOTNOTE")
OCR_EDIT_ACTION = ("TEXT_EDIT", "BOX_MOVE", "BOX_RESIZE", "BOX_CREATE",
                   "BOX_DELETE", "BOX_RESTORE", "RE_OCR", "REORDER",
                   "GROUP_CHANGE", "REVIEW_COMPLETE")
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

    근거는 페이지·좌표가 아니라 reason(판단 근거 서술)으로 표시한다.
    분석기 규격이 텍스트 문자열만 받아 페이지를 알 수 없고, 규격을 바꾸면
    분석기·텍스트 조립·화면 세 파트가 인터페이스 합의를 기다려야 해서
    원문 위치 하이라이트를 범위에서 뺐다.
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
    # 1. OCR 검수   설계안 4.2 · 4.3 · 5.1 · 5.2 를 그대로 반영
    # ═════════════════════════════════════════════════════════════════════
    op.create_table(
        "document_pages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        # 설계안 10-1 — 1 부터 센다. 화면 표시와 일치해 변환이 없다.
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("width", sa.Numeric(10, 2), nullable=False),
        sa.Column("height", sa.Numeric(10, 2), nullable=False),
        # 설계안 9.4 — 좌표 기준본. 프런트가 보는 이미지와 달라지면 박스가 어긋난다.
        # 10-2 는 렌더링본으로 고정하기로 정리했다.
        sa.Column("image_path", sa.String(1000), nullable=False),
        sa.Column("thumbnail_path", sa.String(1000)),
        sa.Column("rotation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("render_scale", sa.Numeric(6, 3)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("document_id", "page_number", name="uq_doc_page"),
        sa.CheckConstraint("page_number >= 1", name="ck_page_number"),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_page_size"),
    )

    # ocr_elements 가 group_id 로 참조하므로 먼저 만든다.
    # 설계안 5.2 는 확장 단계로 뒀지만, 테이블을 나중에 만들면 group_id 의
    # FK 를 나중에 붙여야 한다. 지금 만들어 두고 MVP 에서는 안 쓰면 된다.
    op.create_table(
        "ocr_groups",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.BigInteger(),
                  sa.ForeignKey("document_pages.id", ondelete="CASCADE")),
        sa.Column("group_type", sa.String(20), nullable=False),
        sa.Column("reading_order", sa.Integer(), nullable=False),
        sa.Column("text_override", sa.Text()),
        sa.Column("created_by", sa.BigInteger(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        *timestamps(),
        in_check("group_type", OCR_GROUP_TYPE, "ck_ocr_group_type"),
    )
    op.create_index("ix_ocr_groups_doc", "ocr_groups", ["document_id"])

    op.create_table(
        "ocr_elements",
        # 설계안 9.1 — 수정 후에도 유지되는 식별자.
        # 삭제하고 새로 만들면 이력과 출처 참조가 끊어진다. UPDATE 만 한다.
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.BigInteger(),
                  sa.ForeignKey("document_pages.id", ondelete="CASCADE"),
                  nullable=False),
        # 설계안 4.3 — original_text 는 최초 인식 품질 평가용이라 바꾸지 않는다.
        sa.Column("original_text", sa.String(2000), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        # 픽셀이 아니라 페이지 크기 대비 0~1 비율.
        # 화면 크기와 확대 배율이 달라도 같은 위치에 박스를 표시한다.
        sa.Column("x1", sa.Numeric(9, 6), nullable=False),
        sa.Column("y1", sa.Numeric(9, 6), nullable=False),
        sa.Column("x2", sa.Numeric(9, 6), nullable=False),
        sa.Column("y2", sa.Numeric(9, 6), nullable=False),
        sa.Column("polygon_json", postgresql.JSONB()),
        sa.Column("source", sa.String(20), nullable=False),
        # 설계안 8절 — 데이터 추적 가치가 높아 MVP 부터 저장한다.
        # 어떤 엔진·전처리 조건에서 잘 됐는지 나중에 볼 수 있다.
        sa.Column("ocr_engine", sa.String(30)),
        sa.Column("engine_version", sa.String(30)),
        sa.Column("preprocess_info", postgresql.JSONB()),
        sa.Column("reading_order", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.BigInteger(),
                  sa.ForeignKey("ocr_groups.id", ondelete="SET NULL")),
        sa.Column("review_status", sa.String(20), server_default="UNREVIEWED",
                  nullable=False),
        # 설계안 9.2 — 논리 삭제. 물리 삭제하면 이력과 참조가 사라진다.
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.false(),
                  nullable=False),
        sa.Column("created_by", sa.BigInteger(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", sa.BigInteger(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        *timestamps(),
        # 설계안 4.3 — 동시 수정 충돌 방지. documents.ocr_revision 과 목적이
        # 다르다. 이건 충돌 방지, 저건 파생 데이터 신선도 판정이다.
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        in_check("source", OCR_SOURCE, "ck_ocr_source"),
        in_check("review_status", OCR_REVIEW_STATUS, "ck_ocr_review_status"),
        # 비율 좌표를 DB 가 강제한다. 픽셀 좌표를 넣으면 즉시 막힌다 —
        # 설계안 9.4 가 우려한 '박스 어긋남' 의 가장 흔한 원인이다.
        sa.CheckConstraint(
            "x1 BETWEEN 0 AND 1 AND y1 BETWEEN 0 AND 1 AND "
            "x2 BETWEEN 0 AND 1 AND y2 BETWEEN 0 AND 1",
            name="ck_ocr_bbox_range"),
        sa.CheckConstraint("x1 <= x2 AND y1 <= y2", name="ck_ocr_bbox_order"),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1",
                           name="ck_ocr_confidence"),
        sa.CheckConstraint("version >= 1", name="ck_ocr_version"),
    )
    op.create_index("ix_ocr_order", "ocr_elements", ["document_id", "reading_order"])
    op.create_index("ix_ocr_page", "ocr_elements", ["page_id"])
    op.create_index("ix_ocr_group", "ocr_elements", ["group_id"])
    # 삭제된 박스는 화면과 텍스트 조립에서 제외되므로 인덱스에서도 뺀다.
    op.create_index(
        "ix_ocr_elements_active", "ocr_elements", ["document_id", "reading_order"],
        postgresql_where=sa.text("is_deleted = false"))

    op.create_table(
        "ocr_element_revisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("ocr_element_id", sa.BigInteger(),
                  sa.ForeignKey("ocr_elements.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("before_json", postgresql.JSONB()),
        sa.Column("after_json", postgresql.JSONB()),
        sa.Column("edited_by", sa.BigInteger(),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        in_check("action_type", OCR_EDIT_ACTION, "ck_ocr_edit_action"),
    )
    op.create_index("ix_ocr_rev", "ocr_element_revisions",
                    ["ocr_element_id", "revision_number"])

    # ═════════════════════════════════════════════════════════════════════
    # 2. 분석 산물   금액 · 결정 · 일정
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
    # 3. 산출물   문서를 넣으면 문서가 나온다
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
    op.drop_table("ocr_element_revisions")
    op.drop_table("ocr_elements")
    op.drop_table("ocr_groups")
    op.drop_table("document_pages")