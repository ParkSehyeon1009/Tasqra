# =============================================================================
# 이 파일의 책임: DB 에 저장된 금액 항목을 읽어 프로젝트 금액 현황을 만든다.
#   **계산은 하지 않는다** — 합계·부가세 분리·원가구분 집계·검산은 전부
#   services/amount_calculator.py 가 한다. 이 파일이 하는 일은 셋뿐이다.
#     ① DB 행을 계산기가 요구하는 모양(amount_protocol)으로 바꾼다
#     ② 계산기에 넣을 수 없는 행을 걸러내고 **몇 건인지 센다**
#     ③ 계산 결과를 응답 스키마로 옮긴다
#
# 다른 파일과의 관계: repositories/amount_repository.list_project_items 로 읽고
#   services/amount_calculator 의 aggregate_project·verify_lines 를 부른다.
#   api/routes/amount_router.py 가 이것을 부른다.
#
# Spring 비교: @Service 다. 계산기는 Repository 를 모르는 순수 도메인 서비스이고,
#   이 파일이 그 사이를 잇는 애플리케이션 서비스다.
#
# 왜 이 파일이 필요한가 — 계산 로직은 이미 있었지만 부르는 곳이 없었다
#   amount_calculator 는 테스트 22개로 검증돼 있었는데 **어느 라우터도 부르지
#   않았다.** import 하는 파일조차 없었다. 그래서 기능명세서의 금액 계산·집계가
#   "미구현" 으로 남아 있었다. 이 파일이 그 로직을 처음으로 쓰이게 만든다.
#
# 계산기에 그대로 넘길 수 없는 이유 셋 (전부 조용히 틀리는 종류다)
#   ① category 가 DB 에서는 **문자열**이다. aggregate_by_category 가 `.value` 를
#      부르므로 str 을 넘기면 AttributeError 가 난다 → Enum 으로 바꾼다.
#   ② amount 가 DB 에서 **NULL 일 수 있다**. sum() 이 None 을 만나면 TypeError 로
#      죽는다 → 걸러내고 건수를 응답에 담는다. **0 으로 바꾸지 않는다.**
#   ③ amount·unit_price 가 **Decimal** 이다. 계산기는 int 를 전제한다
#      (금액은 int, 수량은 Decimal — 계산기 머리말) → 변환한다.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.models.amount import AmountItem
from app.models.enums import AmountCategory
from app.repositories.amount_repository import APPROVED_DECISIONS, AmountRepository
from app.schemas.amount_summary import (
    AmountSummaryResponse,
    CategoryTotal,
    DocumentTotalCheck,
    LineMismatch,
)
from app.schemas.amount_item import AmountItemListResponse, AmountItemRow
from app.services.amount_calculator import (
    aggregate_project,
    check_total,
    verify_line,
    verify_lines,
)


@dataclass(frozen=True)
class _Line:
    """계산기에 넘길 한 줄. services/amount_protocol.AmountLine 을 만족한다.

    DB 행을 그대로 쓰지 않는 이유: 위 머리말의 세 가지 변환이 필요하다.
    `item_id` 와 문서 정보는 계산기가 쓰지 않지만, **검산 불일치를 사용자에게
    보여줄 때 어느 항목인지 가리켜야** 하므로 함께 들고 다닌다.
    """

    item_name: str
    category: AmountCategory | None
    quantity: Decimal | None
    unit_price: int | None
    amount: int
    # 계산기의 AmountLine 은 통화를 요구하지 않는다(통화는 문서 단위 개념이다).
    # 그래도 들고 오는 이유: **DB 는 통화를 항목마다 저장한다.** 한 문서 안에서
    # 섞인 경우를 잡으려면 항목 단위로 봐야 한다.
    currency: str
    # --- 계산기는 쓰지 않는다. 결과를 되짚어 보여주기 위한 것이다 -------------
    item_id: int = 0
    document_id: int = 0
    filename: str = ""


@dataclass(frozen=True)
class _Document:
    """문서 하나에서 나온 금액. amount_protocol.AmountDocument 를 만족한다."""

    currency: str
    items: list[_Line] = field(default_factory=list)
    # 문서에 적힌 합계. **리비전 0022 로 담을 곳이 생겼다** —
    # documents.stated_total_amount 다. 그전에는 항상 None 이어서
    # check_total 의 대조가 성립하지 않았다.
    #
    # 여전히 None 일 수 있고 그것이 정상이다. 합계가 적혀 있지 않은 문서가 있다.
    stated_total: int | None = None
    # --- 계산기는 쓰지 않는다. 대조 결과를 되짚어 보여주기 위한 것이다 ----------
    document_id: int = 0
    filename: str = ""


def _to_int(value: Decimal) -> int:
    """Numeric(18,2) 를 계산기가 쓰는 int 로 바꾼다.

    금액은 원 단위라 소수부가 없다. 컬럼이 Numeric(18,2) 인 것은 float 오차를
    피하려는 것이지 전(錢) 단위를 쓰려는 것이 아니다.

    혹시 소수부가 있으면 **반올림한다.** 잘라내면 항목마다 최대 1원이 사라져
    합계가 항목 수만큼 어긋난다. 계산기가 쓰는 ROUND_HALF_UP 과 같은 방식으로
    맞춘다 — 두 곳이 다른 방식으로 반올림하면 검산이 어긋난다.
    """
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class AmountSummaryService:
    def __init__(self, amount_repository: AmountRepository) -> None:
        self._amounts = amount_repository

    def summarize(self, project_id: int) -> AmountSummaryResponse:
        """프로젝트 금액 현황을 만든다 (AMT-002-2 집계 + AMT-002-1 검산).

        승인된 항목만 본다(`APPROVED`·`EDITED`). 그 근거는
        amount_repository.APPROVED_DECISIONS 주석에 있다.

        **문서에 적힌 합계와의 대조(check_total)는 하지 않는다.** 그 값이 DB 에
        없다 — `amount_items` 는 항목만 담고 문서 합계를 저장하지 않는다. 대조는
        추출 시점(LLM 응답을 받은 순간)에만 가능하고, 계약서도 `amount_check` 를
        분석 응답 안에 두고 있다. 여기서 "합계 일치" 를 억지로 만들면 대조하지
        않았는데 대조한 것처럼 보인다.

        **금액 항목이 없어도 오류가 아니다.** 0원과 빈 집계를 돌려준다. 현황
        조회이므로 빈 프로젝트에서 오류 화면이 뜨면 오히려 고장으로 읽힌다.
        `NO_APPROVED_AMOUNTS` 는 산출물 생성처럼 **막아야 하는** 자리에서 쓴다.
        """
        rows = self._amounts.list_project_items(project_id)

        lines: list[_Line] = []
        excluded_no_amount = 0
        for item, document_id, filename in rows:
            if item.amount is None:
                # 문서에 금액이 안 적힌 항목. 0 으로 더하면 합계는 그대로지만
                # "모른다" 는 사실이 사라진다. 건수만 세서 응답에 담는다.
                excluded_no_amount += 1
                continue
            lines.append(self._to_line(item, document_id, filename))

        currency = self._single_currency(lines)

        # 검산은 문서 경계와 무관하다 — 한 줄 안에서 수량 x 단가를 보는 것뿐이다.
        # 그래서 문서로 묶기 전에 한 번에 돌린다.
        mismatches: list[LineMismatch] = []
        unverifiable = 0
        for line, check in zip(lines, verify_lines(lines)):
            if check.matches is None:
                # 수량이나 단가가 없어 검사 자체가 불가능하다. 비율로 산정된
                # 항목(제경비·기술료)이 여기 들어간다 — 오류가 아니다.
                unverifiable += 1
            elif not check.matches:
                mismatches.append(
                    LineMismatch(
                        item_id=line.item_id,
                        document_id=line.document_id,
                        filename=line.filename,
                        item_name=line.item_name,
                        # matches 가 False 면 둘 다 값이 있다.
                        expected=check.expected or 0,
                        actual=check.actual,
                        difference=check.difference or 0,
                    )
                )

        # 문서에 적힌 합계와 대조한다 (리비전 0022 로 담을 곳이 생겼다).
        documents = self._group_by_document(
            lines, currency, self._amounts.stated_totals(project_id)
        )
        aggregate = aggregate_project(documents)
        total_checks, uncomparable = self._check_document_totals(documents)

        return AmountSummaryResponse(
            currency=str(aggregate["currency"]),
            item_total=int(aggregate["item_total"]),
            vat_total=int(aggregate["vat_total"]),
            total_with_vat=int(aggregate["total_with_vat"]),
            by_category=self._to_category_totals(aggregate["by_category"]),
            document_count=int(aggregate["document_count"]),
            included_item_count=len(lines),
            excluded_no_amount=excluded_no_amount,
            unverifiable_line_count=unverifiable,
            line_mismatches=mismatches,
            included_decisions=list(APPROVED_DECISIONS),
            total_checks=total_checks,
            documents_without_stated_total=uncomparable,
        )

    @staticmethod
    def _check_document_totals(
        documents: Sequence[_Document],
    ) -> tuple[list[DocumentTotalCheck], int]:
        """문서마다 «적힌 합계 vs 우리가 더한 합계» 를 대조한다 (AMT-002-1).

        **이 프로젝트에서 정확도를 숫자로 증명할 수 있는 유일한 자리다.** 요약이나
        결정사항은 AI 가 맞게 뽑았는지 확인할 방법이 없지만, 금액은 다시 더해서
        문서에 적힌 값과 맞춰볼 수 있다. `check_total` 의 주석이 그렇게 적고 있다.

        **맞은 문서도 목록에 담는다.** 불일치만 주면 "대조를 했는데 맞았다" 와
        "대조를 안 했다" 를 구별할 수 없다. 앞은 증명이고 뒤는 정보가 없는
        상태인데, 사용자에게는 그 차이가 크다.

        합계가 적혀 있지 않은 문서는 **건수만 센다.** 목록에 넣으면 값이 빈 줄이
        생겨 오류처럼 보인다 — 합계가 없는 문서는 정상이다(공고문·계약서 본문).
        `TotalCheck.comparable` 이 그 구별을 위해 있는 프로퍼티다.
        """
        checks: list[DocumentTotalCheck] = []
        uncomparable = 0
        for document in documents:
            result = check_total(document)
            if not result.comparable:
                uncomparable += 1
                continue
            checks.append(
                DocumentTotalCheck(
                    document_id=document.document_id,
                    filename=document.filename,
                    # comparable 이면 둘 다 값이 있다.
                    stated_total=result.stated_total or 0,
                    item_total=result.item_total,
                    difference=result.difference or 0,
                    matches=result.matches,
                )
            )
        return checks, uncomparable

    def list_items(self, project_id: int, limit: int) -> AmountItemListResponse:
        """금액 항목을 한 줄씩 돌려준다 (AMT-003-3 계산식·산출 근거 표시).

        **summarize 와 같은 저장소 메서드를 쓴다.** 조회 조건이 갈라지면
        "합계는 6건인데 목록은 4줄" 이 된다 — 승인 상태 조건이나 정렬이 한쪽만
        바뀌었을 때 그렇게 되고, 에러가 없어 알아채기 어렵다.

        **금액이 없는 항목도 담는다.** summarize 는 그런 항목을 건수만 세고
        버리지만(`excluded_no_amount`), 목록에서는 어느 항목이 그랬는지 보여야
        한다. 사용자가 확인하려는 것이 바로 그것이다. 대신 `excluded_reason` 에
        왜 빠졌는지 적는다.

        상한을 두는 이유: 산출내역서는 수백 줄이 흔하다. 전부 내려주면 화면을
        펼치는 순간 느려진다. 자를 때는 `total` 을 함께 줘서 화면이 개수를
        잘못 세지 않게 한다.
        """
        rows = self._amounts.list_project_items(project_id)
        visible = rows[:limit]
        items = [
            self._to_row(item, document_id, filename)
            for item, document_id, filename in visible
        ]
        return AmountItemListResponse(
            items=items,
            total=len(rows),
            returned=len(items),
            truncated=len(rows) > len(items),
            limit=limit,
            included_decisions=list(APPROVED_DECISIONS),
        )

    # --- 내부 ---------------------------------------------------------------

    @classmethod
    def _to_row(
        cls, item: AmountItem, document_id: int, filename: str
    ) -> AmountItemRow:
        """DB 행 하나를 화면용 한 줄로 바꾸고 **검산 결과를 붙인다.**

        검산을 여기서 하는 이유는 `verify_line` 이 이미 규칙을 갖고 있어서다 —
        수량·단가 중 하나라도 없으면 `matches=None`, 반올림은 `ROUND_HALF_UP`.
        화면에서 곱하면 그 규칙이 두 곳에 생기고 자바스크립트 부동소수라 큰
        금액에서 1원씩 어긋난다.
        """
        amount = None if item.amount is None else _to_int(item.amount)
        expected: int | None = None
        verified: bool | None = None
        difference: int | None = None
        excluded_reason: str | None = None

        if amount is None:
            # summarize 가 이 항목을 합계에서 뺀 이유를 그대로 적는다.
            excluded_reason = "문서에 금액이 적혀 있지 않아 합계에서 빠졌습니다."
        else:
            check = verify_line(cls._to_line(item, document_id, filename))
            expected = check.expected
            verified = check.matches
            difference = check.difference

        return AmountItemRow(
            id=item.id,
            document_id=document_id,
            filename=filename,
            item_name=item.item_name,
            category=item.category,
            quantity=item.quantity,
            unit=item.unit,
            unit_price=None if item.unit_price is None else _to_int(item.unit_price),
            amount=amount,
            currency=item.currency,
            source_quote=item.source_quote,
            decision=item.decision,
            expected=expected,
            verified=verified,
            difference=difference,
            excluded_reason=excluded_reason,
        )

    @staticmethod
    def _to_line(item: AmountItem, document_id: int, filename: str) -> _Line:
        """DB 행을 계산기가 요구하는 모양으로 바꾼다.

        `AmountCategory(item.category)` 가 실패하면 DB 의 CHECK 제약
        (`ck_amount_category`)과 Enum 이 어긋났다는 뜻이다. **그때는 조용히
        OTHER 로 바꾸지 않고 터지게 둔다** — 모르는 구분을 OTHER 에 섞으면
        원가구분별 합계가 틀린 채로 그럴듯하게 나온다.
        """
        return _Line(
            item_name=item.item_name,
            category=AmountCategory(item.category) if item.category else None,
            quantity=item.quantity,
            unit_price=None if item.unit_price is None else _to_int(item.unit_price),
            amount=_to_int(item.amount),
            currency=item.currency,
            item_id=item.id,
            document_id=document_id,
            filename=filename,
        )

    @staticmethod
    def _single_currency(lines: Sequence[_Line]) -> str:
        """통화가 하나인지 확인하고 그것을 돌려준다.

        `aggregate_project` 도 통화 혼재를 잡지만 그것은 **문서 단위**로만 본다.
        DB 는 통화를 **항목마다** 들고 있어서, 한 문서 안에서 섞이면 그 검사를
        빠져나간다. 그래서 항목 전체로 먼저 확인한다.

        환율을 적용하지 않는 이유는 계산기 주석에 있다 — 어느 시점 환율이냐에
        따라 결과가 달라져 "같은 입력에 같은 결과" 가 깨진다.
        """
        currencies = {line.currency for line in lines}
        if len(currencies) > 1:
            raise BusinessError(ErrorCode.CURRENCY_MISMATCH)
        # 금액 항목이 없으면 통화를 정할 근거가 없다. 계산기의 빈 집계와 같은
        # 기본값을 쓴다 — 두 곳이 다르면 빈 프로젝트에서 통화가 달라 보인다.
        return currencies.pop() if currencies else "KRW"

    @staticmethod
    def _group_by_document(
        lines: Sequence[_Line],
        currency: str,
        stated_totals: dict[int, Decimal] | None = None,
    ) -> list[_Document]:
        """문서별로 묶는다. 문서 수가 집계 결과의 document_count 가 된다.

        리포지토리가 `Document.id` 순으로 정렬해서 주므로 여기서 다시 정렬하지
        않아도 순서가 고정된다.

        `stated_totals` 에 있는 문서만 `stated_total` 이 채워진다. 없으면 None 이고
        `check_total` 이 「대조 불가」로 다룬다 — 그것이 정상 상황이다.
        """
        totals = stated_totals or {}
        grouped: dict[int, _Document] = {}
        for line in lines:
            document = grouped.get(line.document_id)
            if document is None:
                stated = totals.get(line.document_id)
                document = _Document(
                    currency=currency,
                    stated_total=None if stated is None else _to_int(stated),
                    document_id=line.document_id,
                    filename=line.filename,
                )
                grouped[line.document_id] = document
            document.items.append(line)
        return list(grouped.values())

    @staticmethod
    def _to_category_totals(by_category: object) -> list[CategoryTotal]:
        """dict 를 목록으로 바꾼다. **정렬을 고정한다.**

        AMT-002-2 완료 판정이 "같은 입력이면 항상 같은 집계 결과가 나온다" 다.
        dict 순서는 삽입 순서라 항목이 오는 순서가 바뀌면 화면의 줄 순서가
        바뀐다. 금액 내림차순, 같으면 구분 이름 순으로 못 박는다.
        """
        assert isinstance(by_category, dict)
        return [
            CategoryTotal(category=key, amount=value)
            for key, value in sorted(
                by_category.items(), key=lambda pair: (-pair[1], pair[0])
            )
        ]
