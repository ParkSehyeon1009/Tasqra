"""amount_items 에 단가·원가구분 추가

Revision ID: 20260819_0015
Revises: 20260814_0014

왜 필요한가
  리비전 0007 이 amount_items 를 만들 때 두 컬럼이 빠졌는데, 코드는 이미 그
  값을 쓰고 있다. 저장할 곳이 없어서 계산 결과를 한 번 쓰고 버리는 상태다.

    unit_price  services/amount_calculator.py verify_line() 이 수량 x 단가를
                검산한다(AMT-002-1). schemas/amount.py 의 AmountItemOut 에도
                있다. 저장을 못 하면 검산 결과를 남길 수 없고, 근거 변경 탐지·
                재계산(AMT-004-1) 이 비교할 이전 값을 가질 수 없다.
    category    원가구분. models/enums.py 의 AmountCategory 8종이 이미 있고
                schemas/amount.py 가 받는다. 없으면 원가구분별 집계
                (aggregate_by_category · AMT-002-2 · AMT-003-2) 를 저장할 수 없다.

둘 다 nullable 인 이유
  unit_price  제경비·기술료처럼 비율로 산정된 항목은 단가가 원래 없다.
              amount_calculator.verify_line() 이 그 경우 matches=None 을 준다.
  category    LLM 이 원가구분을 판별하지 못하면 비운다. 억지로 OTHER 를 넣으면
              "판별 못 했다" 와 "기타로 판별했다" 를 구별할 수 없다.

값을 만들어 넣지 않는다
  0007 의 원칙을 이어간다 — 문서에 없으면 NULL 이다. 추계(없는 금액 만들기)를
  하지 않고 집계만 하므로 단가 마스터가 없다.

안전한 변경인 이유
  amount_items 는 지금 빈 테이블이다(AMT-001-1 금액 항목 추출이 미구현).
  nullable 컬럼 두 개를 더하는 것이라 기존 데이터가 없고 손실도 없다.
  기존 컬럼·제약·인덱스는 하나도 건드리지 않는다.

ENUM 대신 String + CHECK 를 쓰는 것도 0007 과 같다. 값이 바뀔 때 ALTER TYPE 이
필요 없고, Alembic autogenerate 가 ENUM 변경을 잘 잡지 못한다.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260819_0015"
down_revision = "20260814_0014"
branch_labels = None
depends_on = None

# models/enums.py 의 AmountCategory 와 같아야 한다. 문자열을 두 번 적지 않으려고
# 상수로 뽑았지만, 모델 쪽과 맞는지는 사람이 확인해야 한다(마이그레이션은 앱
# 코드를 import 하지 않는다 — import 하면 모델이 바뀔 때 과거 리비전이 깨진다).
AMOUNT_CATEGORY = (
    "DIRECT_LABOR",   # 직접인건비
    "EXPENSE",        # 직접경비 (여비 · 수용비 등)
    "OVERHEAD",       # 제경비
    "TECH_FEE",       # 기술료
    "MATERIAL",       # 재료비 · 물품비
    "SUBCONTRACT",    # 외주비
    "VAT",            # 부가가치세 — 항목 합계에서 제외한다
    "OTHER",
)


def upgrade() -> None:
    op.add_column(
        "amount_items",
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "amount_items",
        sa.Column("category", sa.String(length=20), nullable=True),
    )

    joined = ", ".join(f"'{value}'" for value in AMOUNT_CATEGORY)
    op.create_check_constraint(
        "ck_amount_category",
        "amount_items",
        f"category IS NULL OR category IN ({joined})",
    )
    # 음수 단가는 문서 오독이거나 부호를 잘못 읽은 것이다. 0 은 허용한다 —
    # 무상 제공 항목이 0원으로 적히는 경우가 있다.
    op.create_check_constraint(
        "ck_amount_unit_price",
        "amount_items",
        "unit_price IS NULL OR unit_price >= 0",
    )

    # 원가구분별 집계(aggregate_by_category)가 이 순서로 조회한다.
    op.create_index("ix_amount_category", "amount_items", ["document_id", "category"])


def downgrade() -> None:
    op.drop_index("ix_amount_category", table_name="amount_items")
    op.drop_constraint("ck_amount_unit_price", "amount_items", type_="check")
    op.drop_constraint("ck_amount_category", "amount_items", type_="check")
    op.drop_column("amount_items", "category")
    op.drop_column("amount_items", "unit_price")
