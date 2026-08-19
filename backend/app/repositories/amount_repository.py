# =============================================================================
# 이 파일의 책임: amount_items 조회를 담당한다. 지금은 과거 유사 사업의 단가
#   선례를 찾는 조회 하나뿐이다(SRH-002-3). 비즈니스 판단은 하지 않는다 —
#   범위를 정하고 중앙값을 내는 것은 services/amount_precedent_service.py 가 한다.
# 다른 파일과의 관계: models/amount.py 의 AmountItem 을 읽는다.
#   documents · projects 를 조인해 문서명·프로젝트명을 함께 가져온다.
#   chunk_repository.search_by_vector 와 같은 이유다 — item.document.project.name
#   으로 접근하면 결과마다 두 단계 지연로딩이 생겨 N+1 이 된다.
# Spring 비교: @Repository 다. 조인해서 DTO 재료를 한 번에 가져오는 것은 JPQL
#   fetch join 이나 프로젝션 쿼리에 해당한다.
# =============================================================================

from __future__ import annotations

from typing import Sequence

from sqlalchemy import Select, select
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
            select(AmountItem, Document.filename, Project.id, Project.name)
            .join(Document, Document.id == AmountItem.document_id)
            .join(Project, Project.id == Document.project_id)
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
