"""산출물 출력 형식에 PDF 추가

이 파일의 책임: deliverables.format CHECK에 PDF를 추가한다. 테이블이나 컬럼은
  바꾸지 않고 허용값만 XLSX·HTML·MD·PDF 네 종류로 확장한다.
다른 파일과의 관계: 액션 태스크 활동 기록 리비전 0020 뒤에 적용되며, ORM의
  app/models/deliverable.py와 같은 형식 목록을 유지한다. 최초 테이블을 만든
  0007은 과거 이력이므로 수정하지 않는다.
Spring 비교: Flyway V21__deliverable_pdf_format.sql처럼 기존 CHECK 제약을 같은
  이름으로 교체하는 데이터베이스 스키마 변경이다.

Revision ID: 20260824_0021
Revises: 20260824_0020
"""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0021"
down_revision = "20260824_0020"
branch_labels = None
depends_on = None

DELIVERABLE_FORMAT = ("XLSX", "HTML", "MD", "PDF")
PREVIOUS_DELIVERABLE_FORMAT = ("XLSX", "HTML", "MD")


def _format_check(values: tuple[str, ...]) -> str:
    joined = ", ".join(f"'{value}'" for value in values)
    return f"format IN ({joined})"


def _replace_format_check(values: tuple[str, ...]) -> None:
    op.drop_constraint(
        "ck_deliverable_format",
        "deliverables",
        type_="check",
    )
    op.create_check_constraint(
        "ck_deliverable_format",
        "deliverables",
        _format_check(values),
    )


def upgrade() -> None:
    _replace_format_check(DELIVERABLE_FORMAT)


def downgrade() -> None:
    # 확인과 제약 교체 사이에 PDF 행이 추가되지 않도록 쓰기를 잠근다.
    op.execute("LOCK TABLE deliverables IN SHARE ROW EXCLUSIVE MODE")
    bind = op.get_bind()
    pdf_exists = bind.execute(
        sa.text("SELECT 1 FROM deliverables WHERE format = 'PDF' LIMIT 1")
    ).scalar_one_or_none()
    if pdf_exists is not None:
        raise RuntimeError(
            "PDF 산출물이 있어 0020으로 내릴 수 없습니다. "
            "PDF 행을 보존하거나 변환한 뒤 다시 시도하세요."
        )
    _replace_format_check(PREVIOUS_DELIVERABLE_FORMAT)
