# =============================================================================
# 이 파일의 책임: amount_items 조회를 담당한다. 둘 있다 — 과거 유사 사업의 단가
#   선례(SRH-002-3)와 한 프로젝트의 금액 항목 전부(AMT-002-2 집계의 재료).
#   비즈니스 판단은 하지 않는다 — 범위를 정하고 중앙값을 내는 것은
#   services/amount_precedent_service.py, 합계와 검산은
#   services/amount_summary_service.py 가 한다.
#
#   다만 **"어느 분석의 항목을 볼 것인가" 는 여기서 정한다.** 재분석으로 쌓인 옛
#   항목을 거르는 일인데, 서비스마다 각자 걸러야 하면 한 곳이 빠뜨리는 순간 그
#   화면만 금액이 두 배로 나온다. 조회 조건이라 리포지토리가 맞다.
# 다른 파일과의 관계: models/amount.py 의 AmountItem 을 읽는다.
#   documents · projects 를 조인해 문서명·프로젝트명을 함께 가져온다.
#   chunk_repository.search_by_vector 와 같은 이유다 — item.document.project.name
#   으로 접근하면 결과마다 두 단계 지연로딩이 생겨 N+1 이 된다.
# Spring 비교: @Repository 다. 조인해서 DTO 재료를 한 번에 가져오는 것은 JPQL
#   fetch join 이나 프로젝션 쿼리에 해당한다.
# =============================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.amount import AmountItem
from app.models.document import Analysis, Document
from app.models.project import Project

# 현황·선례·산출물에 실제로 담는 승인 상태. PENDING(아직 사람이 안 본 것)과
# REJECTED 는 제외한다. EDITED 는 사람이 값을 고쳐 확정한 것이므로 포함한다.
APPROVED_DECISIONS = ("APPROVED", "EDITED")

# 분석 하나가 검토 완료됐다고 보는 상태. 승인된 항목이 0건이어도 REJECTED 로 모두
# 결정했다면 그 분석은 유효 스냅샷이다. 그래야 과거 승인 금액으로 되돌아가지 않는다.
FINALIZED_AMOUNT_DECISIONS = (*APPROVED_DECISIONS, "REJECTED")
_AMOUNT_ANALYZER_TYPE = "amount"


def effective_amount_analysis_subquery():
    """문서마다 PENDING이 없는 가장 최신 금액 분석을 고른다.

    금액 분석 한 번의 모든 행은 같은 ``analysis_id``를 가진 스냅샷이다. 최신 분석에
    PENDING이 하나라도 있으면 아직 검토 중이므로 직전 완료 분석을 유지하고, 모든
    행이 APPROVED·EDITED·REJECTED 중 하나가 된 뒤에만 새 분석으로 전환한다.
    전부 REJECTED이거나 추출 결과가 0행인 분석도 완료 스냅샷이므로 ``analyses``를
    기준으로 고른다. 승인 행을 기준으로 고르면 이 두 경우에 과거 값이 되살아난다.
    단, 재분석 때 PENDING 행이 삭제되어 비어 버리거나 일부 승인 행만 남은 과거
    분석과 구별하려고 현재 행 수가 ``result_json.items``의 원래 추출 건수와 같은
    분석만 완료 후보로 인정한다.

    ``MAX(Analysis.id)``는 자동 증가 PK라 생성 순서를 나타낸다. ``created_at``은
    같은 시각일 수 있어 최신 판정에 쓰지 않는다.

    Spring 비교: Analysis를 기준으로 ``NOT EXISTS (미결 AmountItem)``를 건 뒤
    문서별 MAX(id)를 구하는 JPQL 파생 테이블과 같다.
    """
    unresolved_item = (
        select(AmountItem.id)
        .where(
            AmountItem.analysis_id == Analysis.id,
            or_(
                AmountItem.decision.is_(None),
                AmountItem.decision.not_in(FINALIZED_AMOUNT_DECISIONS),
            ),
        )
        .correlate(Analysis)
        .exists()
    )
    persisted_item_count = (
        select(func.count())
        .select_from(AmountItem)
        .where(AmountItem.analysis_id == Analysis.id)
        .correlate(Analysis)
        .scalar_subquery()
    )
    # AmountWriter는 재분석할 때 이전 PENDING 행만 지우고 Analysis 이력은 남긴다.
    # 현재 행 수가 원래 추출한 result_json.items 수와 같아야만 완료 후보로 본다.
    # 그래야 전부/일부 PENDING이 삭제된 과거 분석을 정상 완료본으로 오인하지 않고,
    # 실제 0행 추출(0 == 0)은 새 0건 스냅샷으로 전환할 수 있다.
    extracted_item_count = func.jsonb_array_length(
        Analysis.result_json["items"].as_json()
    )
    return (
        select(
            Analysis.document_id.label("document_id"),
            func.max(Analysis.id).label("analysis_id"),
        )
        .where(Analysis.analyzer_type == _AMOUNT_ANALYZER_TYPE)
        .where(~unresolved_item)
        .where(persisted_item_count == extracted_item_count)
        .group_by(Analysis.document_id)
        .subquery()
    )


def apply_effective_amount_snapshot(stmt: Select) -> Select:
    """금액 SELECT에 모든 소비처가 공유하는 유효 스냅샷 조건을 붙인다.

    정식 스키마에서 ``analysis_id``는 NOT NULL이고 AmountWriter만 행을 만든다.
    다만 제약 도입 전 수동 적재·스키마 드리프트로 NULL 행이 이미 있다면 독립 수동
    항목으로 보존한다. 즉 승인된 NULL 행은 분석 교체 대상이 아니며 항상 포함하고,
    분석에 속한 행만 문서별 유효 analysis 하나로 제한한다.

    이 함수를 현황·선례·산출물 count/list가 함께 써야 숫자가 갈리지 않는다.
    Spring 비교: 여러 Repository 메서드가 공유하는 Specification을 적용한 것이다.
    """
    effective = effective_amount_analysis_subquery()
    return stmt.outerjoin(
        effective,
        and_(
            AmountItem.document_id == effective.c.document_id,
            AmountItem.analysis_id == effective.c.analysis_id,
        ),
    ).where(
        or_(
            AmountItem.analysis_id == effective.c.analysis_id,
            AmountItem.analysis_id.is_(None),
        )
    )


class AmountRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add_items(self, rows: list[AmountItem]) -> list[AmountItem]:
        """검증된 금액 행을 현재 외부 트랜잭션에 추가하고 PK를 확정한다."""
        if rows:
            self._db.add_all(rows)
            self._db.flush()
        return rows

    def delete_pending_items(self, document_id: int) -> int:
        """재분석 전 같은 문서의 미검토 금액만 삭제한다."""
        return self._db.query(AmountItem).filter(
            AmountItem.document_id == document_id,
            AmountItem.decision == "PENDING",
        ).delete(synchronize_session=False)

    def list_precedents(
        self,
        *,
        item_name: str,
        project_ids: Sequence[int],
        limit: int,
    ) -> list[tuple[AmountItem, str, int, str]]:
        """다른 프로젝트에서 같은(또는 비슷한) 항목명의 단가 선례를 찾는다.

        (금액 항목, 문서 파일명, 프로젝트 id, 프로젝트 이름) 을 돌려준다.

        조건 넷이 모두 필요하다.

        조건 넷 말고 하나가 더 있다 — **재분석으로 쌓인 옛 항목을 뺀다**
        (`apply_effective_amount_snapshot`). 없으면 같은 문서를 두 번 분석했을 때 같은
        항목이 목록에 두 번 나와 중앙값이 그쪽으로 끌린다.

        1. project_id IN project_ids
           호출한 쪽이 "내 멤버십 − 현재 프로젝트" 를 계산해서 넘긴다. 여기서
           멤버십을 다시 확인하지 않는다 — 리포지토리가 권한을 판단하면 판단
           지점이 두 곳이 되어 어긋난다.

        2. decision IN APPROVED_DECISIONS
           승인된 것만 선례로 쓴다. 이유는 위 상수 주석에 있다.

        3. unit_price IS NOT NULL
           찾는 것이 **단가** 선례다. 제경비·기술료처럼 비율로 산정된 항목은
           단가가 원래 없어서 선례가 될 수 없다. 그 항목의 비율은 우리가
           저장하지 않는다(문서에 적힌 금액만 읽는다).

        4. 항목명 일치
           완전일치를 먼저, 부분일치(ILIKE)를 그다음에 둔다. "특급기술자" 와
           "특급 기술자" 정도는 잡히지만 "1급 기술자" 는 못 잡는다. 뜻으로
           맞추려면 임베딩이 필요하고, 그것이 SRH-002-3 의 "유사" 를 제대로
           구현하는 부분이라 여기서는 문자열까지만 한다.

        정렬은 완전일치 먼저, 그다음 단가 내림차순이다. 사람이 "가장 비쌌던
        선례" 부터 보는 것이 판단에 낫다고 봤다.
        """
        if not project_ids:
            return []

        exact = item_name.strip()
        pattern = f"%{exact}%"

        stmt: Select = (
            apply_effective_amount_snapshot(
                select(AmountItem, Document.filename, Project.id, Project.name)
                .join(Document, Document.id == AmountItem.document_id)
                .join(Project, Project.id == Document.project_id)
            )
            .where(Document.project_id.in_(project_ids))
            .where(AmountItem.decision.in_(APPROVED_DECISIONS))
            .where(AmountItem.unit_price.isnot(None))
            .where(
                (AmountItem.item_name == exact)
                | (AmountItem.item_name.ilike(pattern))
            )
            # 완전일치가 먼저 오게 한다. bool 을 정렬키로 쓰면 False<True 이므로
            # desc() 를 붙여 True 를 앞으로 보낸다.
            .order_by(
                (AmountItem.item_name == exact).desc(),
                AmountItem.unit_price.desc(),
            )
            .limit(limit)
        )
        return [
            (row[0], row[1], int(row[2]), row[3])
            for row in self._db.execute(stmt).all()
        ]

    def get_item(
        self, project_id: int, item_id: int
    ) -> tuple[AmountItem, int, str] | None:
        """금액 항목 하나를 문서 정보와 함께 가져온다. 없으면 None.

        **`project_id` 로 반드시 함께 거른다.** 항목 id 만으로 찾으면 다른
        프로젝트의 금액을 id 만 바꿔서 읽을 수 있다(수평 권한 상승). 경로에
        프로젝트가 있고 의존성이 멤버십을 확인했더라도, 조회가 그 범위를 다시
        좁혀야 한다 — 확인하는 곳과 읽는 곳이 다르면 어긋난다.

        **승인 상태로 거르지 않는다.** 이 메서드는 「이 항목이 무엇인가」를 묻는
        것이고, 승인 여부로 무엇을 할지는 부르는 쪽이 정한다.

        Spring 비교: `findByIdAndDocument_Project_Id(...)` 처럼 소유 관계를 쿼리에
        박아 두는 것과 같다.
        """
        stmt: Select = (
            select(AmountItem, Document.id, Document.filename)
            .join(Document, Document.id == AmountItem.document_id)
            .where(Document.project_id == project_id)
            .where(AmountItem.id == item_id)
        )
        row = self._db.execute(stmt).first()
        if row is None:
            return None
        return (row[0], int(row[1]), row[2])

    def stated_totals(self, project_id: int) -> dict[int, Decimal]:
        """문서에 적힌 합계를 {문서 id: 합계} 로 준다 (리비전 0022).

        **적혀 있는 문서만 담는다.** NULL 을 0 으로 바꿔 담지 않는다 — 그러면
        "합계가 0원인 문서" 와 구별되지 않고, 대조가 늘 불일치로 나온다. 없는
        문서는 키 자체가 없어서 호출부가 `.get()` 으로 «대조 불가» 를 판단한다.

        `list_project_items` 의 튜플을 넓히지 않고 **별도 조회로 둔 이유**: 금액
        항목 목록(`AMT-003-3`)에는 문서 합계가 필요 없다. 튜플에 끼우면 그 화면도
        쓰지 않는 값을 들고 다니게 되고, 튜플 자리 수가 늘어 부르는 곳마다 고쳐야
        한다.

        Spring 비교: 같은 트랜잭션 안의 두 번째 조회다. JPA 라면
        `Map<Long, BigDecimal>` 로 받는 프로젝션 쿼리에 해당한다.
        """
        stmt: Select = (
            select(Document.id, Document.stated_total_amount)
            .where(Document.project_id == project_id)
            .where(Document.stated_total_amount.isnot(None))
        )
        return {int(row[0]): row[1] for row in self._db.execute(stmt).all()}

    def list_project_items(
        self, project_id: int
    ) -> list[tuple[AmountItem, int, str]]:
        """한 프로젝트의 **승인된** 금액 항목 전부를 문서 정보와 함께 가져온다.

        (금액 항목, 문서 id, 문서 파일명) 을 돌려준다. 프로젝트 금액 집계
        (AMT-002-2)와 수량x단가 검산(AMT-002-1)의 재료다.

        list_precedents 와 다른 점 셋

        1. **`unit_price IS NOT NULL` 조건이 없다.** 선례는 단가를 찾는 것이라
           단가 없는 항목이 쓸모없지만, 집계는 금액을 더하는 것이라 제경비·
           기술료처럼 비율로 산정된 항목도 반드시 들어가야 한다. 빼면 합계가
           조용히 낮아진다.

        2. **항목명으로 걸지 않는다.** 프로젝트의 모든 금액이 대상이다.

        3. **다른 프로젝트를 보지 않는다.** 선례는 "내 멤버십 − 현재 프로젝트"
           였지만 여기는 현재 프로젝트 하나뿐이다.

        **재분석으로 쌓인 옛 항목은 뺀다** (`apply_effective_amount_snapshot`). 이것이
        없으면 문서를 두 번 분석했을 때 금액이 두 배가 된다. 선례 조회도 같은
        조건을 쓴다 — 한쪽만 고치면 두 화면의 숫자가 설명할 수 없게 달라진다.

        `amount IS NULL` 인 항목도 **가져온다.** 문서에 금액이 안 적힌 항목이
        그렇다(계약서: "amount 가 null 인 항목을 그대로 둔다"). 합계에 못 넣는
        것은 맞지만, **몇 건이 빠졌는지 사용자에게 알려야** 하므로 여기서 버리지
        않는다. 거르는 것은 서비스가 하고 그 건수를 응답에 담는다.

        정렬을 고정하는 이유: AMT-002-2 완료 판정이 "같은 입력이면 항상 같은
        집계 결과가 나온다" 다. 합계는 순서와 무관하지만 **검산 불일치 목록은
        순서가 보이므로** 정렬이 없으면 호출마다 뒤바뀐다.
        """
        stmt: Select = (
            apply_effective_amount_snapshot(
                select(AmountItem, Document.id, Document.filename)
                .join(Document, Document.id == AmountItem.document_id)
            )
            .where(Document.project_id == project_id)
            .where(AmountItem.decision.in_(APPROVED_DECISIONS))
            .order_by(Document.id, AmountItem.id)
        )
        return [
            (row[0], int(row[1]), row[2])
            for row in self._db.execute(stmt).all()
        ]

    def list_pending_items(
        self, project_id: int
    ) -> list[tuple[AmountItem, int, str]]:
        """승인 **대기(PENDING)** 금액 항목을 문서 정보와 함께 가져온다.

        (금액 항목, 문서 id, 문서 파일명) 을 돌려준다. 「승인 대기」 화면
        (AMT-001-2)이 이걸로 목록을 만들고, 사람이 승인·거절·수정한다.

        `list_project_items` 와 다른 점 둘

        1. **decision == 'PENDING'** 만 본다. 그쪽은 이미 승인된 것만 봤다.

        2. **`apply_effective_amount_snapshot` 로 거르지 않는다.** 그 helper는
           현황·선례·산출물처럼 승인된 현재값을 읽는 소비처용이다. 최신 분석에
           PENDING이 있으면 직전 완료 분석으로 물러나므로, 대기 목록에 적용하면
           사람이 지금 검토해야 할 최신 항목이 숨는다. 승인·거절 UI 동작을
           유지하기 위해 모든 PENDING을 그대로 보여준다.

        `amount IS NULL` 인 항목도 가져온다 — 금액이 안 적힌 항목도 사람이 보고
        승인·거절해야 한다. 정렬을 고정하는 이유는 list_project_items 와 같다.
        """
        stmt: Select = (
            select(AmountItem, Document.id, Document.filename)
            .join(Document, Document.id == AmountItem.document_id)
            .where(Document.project_id == project_id)
            .where(AmountItem.decision == "PENDING")
            .order_by(Document.id, AmountItem.id)
        )
        return [
            (row[0], int(row[1]), row[2])
            for row in self._db.execute(stmt).all()
        ]

    def list_rejected_items(
        self, project_id: int
    ) -> list[tuple[AmountItem, int, str]]:
        """**거절된(REJECTED)** 금액 항목을 문서 정보와 함께 가져온다.

        거절은 데이터를 지우지 않고 `decision='REJECTED'` 로 둘 뿐이라, 실수로
        거절한 것을 되살릴 수 있어야 한다. 이 목록이 그 「거절함(휴지통)」이다.
        되살리기는 `AmountItemService.cancel`(→PENDING)을 그대로 쓴다.

        `list_pending_items` 와 같은 구조(최신분석 필터 없이 문서·항목 순서)다.
        집계·대기 어디에도 세지 않는 별개 조회라 화면 맨 아래 접힌 섹션에서만 쓴다.
        """
        stmt: Select = (
            select(AmountItem, Document.id, Document.filename)
            .join(Document, Document.id == AmountItem.document_id)
            .where(Document.project_id == project_id)
            .where(AmountItem.decision == "REJECTED")
            .order_by(Document.id, AmountItem.id)
        )
        return [
            (row[0], int(row[1]), row[2])
            for row in self._db.execute(stmt).all()
        ]
