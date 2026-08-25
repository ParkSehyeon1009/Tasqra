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

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.amount import AmountItem
from app.models.document import Document
from app.models.project import Project

# 선례로 인정할 승인 상태. PENDING(아직 사람이 안 본 것)과 REJECTED 는 제외한다.
#
# AMT-001-2 완료 판정이 "승인 전에는 어디에도 반영되지 않고" 다. 승인 안 된
# 추출값을 다른 사업의 근거로 쓰면 그 원칙이 깨진다. EDITED 는 사람이 값을
# 고쳐 확정한 것이라 포함한다 — 오히려 신뢰도가 더 높다.
APPROVED_DECISIONS = ("APPROVED", "EDITED")


def _latest_approved_analysis():
    """문서마다 **승인된 항목이 있는 가장 최신 분석**만 남기는 서브쿼리.

    ### 왜 필요한가 — 없으면 금액이 두 배가 된다

    문서를 다시 분석하면 `analyses` 에 새 행이 쌓이고(`DOC-006-2`) 금액 항목도
    새로 생긴다. 옛 항목은 지워지지 않는다. 그래서 이 조건이 없으면 **같은 문서의
    금액이 분석 횟수만큼 더해진다.**

    에러가 나지 않고 합계만 조용히 커진다. 사업 규모를 잘못 보고하는 종류의
    사고다. `models/amount.py` 의 `analysis_id` 주석이 *"이 값으로 최신 분석의
    금액과 과거 것을 구별한다"* 고 적어 둔 것이 이 조건을 뜻한다 — **의도는
    적혀 있었고 쿼리에 없었다.**

    ### `MAX(analysis_id)` 로 최신을 고르는 근거

    `analyses.id` 가 `BigInteger` 자동증가라 나중에 만든 행이 항상 크다.
    `created_at` 으로 고르면 같은 초에 두 번 분석했을 때 순서가 흔들린다.

    ### 승인 상태로 먼저 거르는 이유

    분석 #2 를 돌렸지만 아직 아무도 승인하지 않았고 #1 은 승인돼 있다고 하자.
    승인 여부를 보지 않고 최신(#2)을 고르면 승인 필터를 거친 뒤 **0건이 되어
    금액이 화면에서 사라진다.** 사용자는 승인해 둔 값이 없어졌다고 읽는다.
    그래서 "승인된 항목이 있는 분석 중 가장 최신" 을 고른다.

    ### 다른 곳에서도 같은 조건을 써야 한다

    `list_precedents` 와 `list_project_items` 가 **같은 서브쿼리를 쓴다.** 한쪽만
    고치면 선례에는 같은 항목이 두 번 나오는데 집계는 한 번 세는, 설명할 수 없는
    상태가 된다.

    Spring 비교: JPQL 의 상관 서브쿼리(`WHERE a.analysisId = (SELECT MAX(...))`)를
    조인 가능한 파생 테이블로 바꾼 것이다. 조인이라 문서마다 한 번만 계산된다.
    """
    return (
        select(
            AmountItem.document_id.label("document_id"),
            func.max(AmountItem.analysis_id).label("analysis_id"),
        )
        # 승인 상태만 여기서 거른다. unit_price 같은 «쓸 수 있는 값인가» 조건은
        # 넣지 않는다 — 그것은 어느 분석이 최신인지와 무관하고, 넣으면 단가 없는
        # 항목만 있는 최신 분석이 건너뛰어진다.
        .where(AmountItem.decision.in_(APPROVED_DECISIONS))
        .group_by(AmountItem.document_id)
        .subquery()
    )


class AmountRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

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
        (`_latest_approved_analysis`). 없으면 같은 문서를 두 번 분석했을 때 같은
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

        latest = _latest_approved_analysis()
        stmt: Select = (
            select(AmountItem, Document.filename, Project.id, Project.name)
            .join(Document, Document.id == AmountItem.document_id)
            .join(Project, Project.id == Document.project_id)
            # 재분석으로 쌓인 옛 항목을 뺀다. 없으면 같은 문서의 같은 항목이
            # 선례 목록에 분석 횟수만큼 나와 중앙값을 끌어당긴다.
            .join(
                latest,
                and_(
                    AmountItem.document_id == latest.c.document_id,
                    AmountItem.analysis_id == latest.c.analysis_id,
                ),
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

        **재분석으로 쌓인 옛 항목은 뺀다** (`_latest_approved_analysis`). 이것이
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
        latest = _latest_approved_analysis()
        stmt: Select = (
            select(AmountItem, Document.id, Document.filename)
            .join(Document, Document.id == AmountItem.document_id)
            # 재분석으로 쌓인 옛 항목을 뺀다. 없으면 합계가 분석 횟수만큼
            # 불어난다 — _latest_approved_analysis 주석 참고.
            .join(
                latest,
                and_(
                    AmountItem.document_id == latest.c.document_id,
                    AmountItem.analysis_id == latest.c.analysis_id,
                ),
            )
            .where(Document.project_id == project_id)
            .where(AmountItem.decision.in_(APPROVED_DECISIONS))
            .order_by(Document.id, AmountItem.id)
        )
        return [
            (row[0], int(row[1]), row[2])
            for row in self._db.execute(stmt).all()
        ]
