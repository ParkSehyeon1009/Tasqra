"""문서에 적힌 금액 합계 컬럼 추가

이 파일의 책임: documents 에 stated_total_amount 를 더한다. 문서 아래쪽 「합계」
  칸에 적혀 있는 값이고, 우리가 항목을 더한 합계와 대조하는 기준이 된다
  (AMT-002-1 금액 계산·합계 검증).
다른 파일과의 관계: 산출물 PDF 형식 리비전 0021 뒤에 적용된다. ORM 은
  app/models/document.py 의 Document.stated_total_amount 이고, 이 값을 쓰는 것은
  services/amount_calculator.py 의 check_total() 이다.
Spring 비교: Flyway V22__document_stated_total.sql 에 해당한다. nullable 컬럼
  추가라 기존 행을 건드리지 않으므로 잠금 시간이 사실상 없다.

왜 이 컬럼이 필요한가 — 이미 있는 로직이 죽어 있었다
  check_total() 은 단위테스트 4개로 검증돼 있는데 **제품 코드에서 아무도 부르지
  못했다.** amount_items 는 항목만 담고 문서의 합계는 어디에도 저장하지 않아서
  대조할 상대가 없었기 때문이다. 그 함수 주석이 이렇게 적고 있다 —
  "이 프로젝트에서 정확도를 수치로 증명할 수 있는 유일한 기능이다."
  요약이나 결정사항은 AI 가 맞게 뽑았는지 확인할 방법이 없지만 금액은 재계산해
  대조된다. 컬럼 하나로 그 기능이 살아난다.

왜 documents 에 두는가
  문서 하나에 합계는 하나다. amount_items 에 두면 항목마다 같은 값이 복제되고,
  한 항목만 고쳐지면 어느 것이 맞는지 알 수 없게 된다.
  analyses.result_json 에서 읽는 방법도 있었지만 JSONB 를 파싱해야 하고 인덱스를
  걸 수 없어서 "값은 있는데 꺼내기 어렵다" 로 남는다.

왜 nullable 인가
  합계가 적혀 있지 않은 문서가 정상적으로 있다(공고문·계약서 본문). 0 을 넣으면
  "합계가 0원인 문서" 와 "합계가 안 적힌 문서" 를 구별할 수 없고, 대조가 항상
  불일치로 나온다. TotalCheck 가 stated_total=None 을 「대조 불가」로 따로 다루는
  것도 같은 이유다 — 대조 불가는 정상이고 불일치는 확인이 필요한 문제다.

왜 Numeric(18,2) 인가
  amount_items.amount 와 같은 형이다. 형이 다르면 계산기에 넘길 때 변환 규칙이
  둘이 되고, 반올림이 어긋나 검산이 1원씩 틀린다.

Revision ID: 20260825_0022
Revises: 20260824_0021
"""

import sqlalchemy as sa
from alembic import op

revision = "20260825_0022"
down_revision = "20260824_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("stated_total_amount", sa.Numeric(18, 2), nullable=True),
    )
    # 음수 합계는 문서에 적힐 수 없다. 0 은 허용한다 — 실제로 0원짜리 내역서가
    # 있을 수 있고, 그것과 "안 적혀 있다"(NULL) 는 이 컬럼에서 구별된다.
    op.create_check_constraint(
        "ck_document_stated_total",
        "documents",
        "stated_total_amount IS NULL OR stated_total_amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_document_stated_total", "documents", type_="check")
    op.drop_column("documents", "stated_total_amount")
