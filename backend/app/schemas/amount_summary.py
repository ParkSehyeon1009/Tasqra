# =============================================================================
# 이 파일의 책임: 프로젝트 금액 현황 API 의 응답 스키마를 정의한다
#   (AMT-002-2 집계 · AMT-002-1 검산을 조회로 노출한 것).
#
# 다른 파일과의 관계: api/routes/amount_router.py 가 이 스키마를 돌려주고
#   services/amount_summary_service.py 가 채운다. 계산은 전부
#   services/amount_calculator.py 가 한다 — 여기서 더하지 않는다.
#
# Spring 비교: @RestController 의 Response DTO 다.
#
# 왜 "빠진 것" 을 응답에 담는가
#   합계만 주면 사용자는 그것이 전부라고 읽는다. 그런데 금액이 안 적힌 항목과
#   승인 안 된 항목은 합계에 없다. 그 사실을 함께 주지 않으면 **합계가 낮은 것을
#   사업이 작은 것으로 오해한다.** 대시보드에서 열린 태스크를 0 이 아니라 null 로
#   둔 것과 같은 판단이다 — 모르는 것을 아는 것처럼 보이게 하지 않는다.
# =============================================================================

from pydantic import BaseModel, Field

__all__ = [
    "AmountSummaryResponse",
    "CategoryTotal",
    "LineMismatch",
]


class CategoryTotal(BaseModel):
    """원가 구분별 합계. 구분이 없던 항목은 OTHER 로 모인다."""

    category: str
    amount: int


class LineMismatch(BaseModel):
    """수량 x 단가가 문서에 적힌 금액과 맞지 않은 항목.

    **금액을 고쳐서 담지 않는다.** 문서가 틀렸다는 사실을 그대로 보고한다
    (AMT-002-1 원칙). 어느 쪽이 맞는지는 사람이 정한다.
    """

    item_id: int
    document_id: int
    filename: str
    item_name: str
    # 수량 x 단가
    expected: int
    # 문서에 적힌 금액
    actual: int
    # expected - actual. 양수면 문서 금액이 작게 적혀 있다.
    difference: int


class DocumentTotalCheck(BaseModel):
    """문서에 적힌 합계와 우리가 더한 합계를 대조한 결과 (AMT-002-1).

    **맞은 문서도 담는다.** 불일치만 주면 "대조했고 맞았다" 와 "대조를 안 했다" 가
    구별되지 않는다. 앞은 정확도의 증명이고 뒤는 정보가 없는 상태다.

    합계가 적혀 있지 않은 문서는 여기 들어오지 않고 `documents_without_stated_total`
    에 세어진다 — 그것은 오류가 아니라 정상 상황이다.
    """

    document_id: int
    filename: str
    # 문서 아래쪽 「합계」 칸에 적힌 값 (documents.stated_total_amount, 리비전 0022).
    stated_total: int
    # 우리가 항목을 더한 값. **부가세는 빠져 있다** — 부가세를 포함해 비교하면
    # 공급가액 합계가 적힌 문서에서 늘 불일치가 난다.
    item_total: int
    # item_total - stated_total. **양수면 문서에 적힌 합계가 작다.**
    # verify_line 의 difference 와 같은 방향이다(계산값 − 문서값). 두 곳이 반대면
    # 화면이 어느 쪽인지 외워야 한다.
    difference: int
    matches: bool


class AmountSummaryResponse(BaseModel):
    currency: str
    # 부가세를 **제외한** 항목 합계. 부가세를 함께 더하면 이중 계산이 된다.
    item_total: int
    vat_total: int
    total_with_vat: int
    by_category: list[CategoryTotal]
    # 금액 항목이 하나라도 있는 문서 수. 프로젝트의 전체 문서 수가 아니다.
    document_count: int
    # 합계에 들어간 항목 수.
    included_item_count: int

    # --- 합계에 들어가지 않은 것 -------------------------------------------
    # 문서에 금액이 안 적혀 있어 더할 수 없던 항목 수. **0 으로 취급하지 않는다** —
    # 0 으로 더하면 합계는 맞아 보이지만 "금액을 모른다" 는 사실이 사라진다.
    excluded_no_amount: int
    # 수량이나 단가가 없어 검산할 수 없던 항목 수. 제경비·기술료처럼 비율로
    # 산정된 항목이 여기 들어간다 — 오류가 아니다.
    unverifiable_line_count: int
    # 수량 x 단가와 금액이 어긋난 항목. 빈 목록이면 모두 맞았다는 뜻이다.
    line_mismatches: list[LineMismatch] = Field(default_factory=list)

    # 집계에 포함한 승인 상태. PENDING·REJECTED 는 빠진다 — 승인 전에는 어디에도
    # 반영하지 않는다(AMT-001-2 완료 판정). 화면이 "승인된 항목만" 이라고 적을 수
    # 있도록 서버가 알려준다.
    included_decisions: list[str]

    # --- 문서에 적힌 합계와의 대조 (리비전 0022 로 가능해졌다) ----------------
    # 문서마다 한 줄. 맞은 것도 담는다 — DocumentTotalCheck 주석 참고.
    total_checks: list[DocumentTotalCheck] = Field(default_factory=list)
    # 합계가 적혀 있지 않아 대조하지 못한 문서 수. **오류가 아니다** — 공고문처럼
    # 합계가 없는 문서가 정상적으로 있다. 0 으로 취급하지 않는 이유는
    # models/document.py 의 stated_total_amount 주석에 있다.
    documents_without_stated_total: int = 0
