# =============================================================================
# 이 파일의 책임: 과거 유사 사업의 단가 선례를 찾는다(SRH-002-3). 범위를 정하고
#   (내 멤버십 − 현재 프로젝트), 리포지토리 결과를 응답으로 바꾸고, 중앙값을 낸다.
# 다른 파일과의 관계: repositories/amount_repository.py 로 조회하고
#   repositories/project_repository.py 로 내 멤버십을 확인한다. 응답 계약은
#   schemas/amount_precedent.py 다.
# Spring 비교: @Service 다. 범위 계산이 SearchService._resolve_scope 와 같은
#   일을 하지만 "현재 프로젝트를 뺀다" 는 점이 다르다.
#
# 검색 API 를 고치지 않은 이유
#   의미 검색(POST /api/search)은 project_ids 로 부분집합을 받는다. 그래서
#   "내 멤버십 − 현재" 를 넘기면 그것만으로도 과거 사업 문서를 찾을 수 있다.
#   그런데 이 기능이 돌려줘야 하는 것은 **문장이 아니라 단가 숫자**다
#   (SRH-002-3 완료 판정: "과거 사업의 단가가 출처와 함께 표시된다").
#   의미 검색은 청크 텍스트를 주므로 "특급기술자 3인월 8,800,000 26,400,000"
#   이라는 문장까지는 오지만 단가 8,800,000 을 뽑아내지는 못한다. 그래서
#   amount_items 를 직접 조회한다. 두 기능은 서로를 대체하지 않는다.
# =============================================================================

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.amount_repository import AmountRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.amount_precedent import (
    AmountPrecedentItem,
    AmountPrecedentResponse,
    AmountPrecedentSummary,
)

logger = logging.getLogger(__name__)


def median(values: list[Decimal]) -> Decimal:
    """중앙값. 짝수 개면 가운데 둘의 평균이다.

    statistics.median 을 쓰지 않는 이유는 float 로 바꾸지 않기 위해서다.
    Decimal 끼리의 나눗셈은 Decimal 을 주므로 금액 정밀도가 유지된다.
    """
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


class AmountPrecedentService:
    def __init__(
        self,
        db: Session,
        amount_repository: AmountRepository,
        project_repository: ProjectRepository,
    ) -> None:
        self._db = db
        self._amounts = amount_repository
        self._projects = project_repository

    def find_precedents(
        self,
        *,
        user_id: int,
        current_project_id: int,
        item_name: str,
        limit: int,
    ) -> AmountPrecedentResponse:
        scope = self._resolve_scope(user_id, current_project_id)
        if not scope:
            # 내가 멤버인 다른 프로젝트가 없다. 오류가 아니라 "선례 없음" 이다.
            logger.info(
                "단가 선례를 찾을 다른 프로젝트가 없다 user_id=%s current=%s",
                user_id,
                current_project_id,
            )
            return AmountPrecedentResponse(
                item_name=item_name, searched_project_ids=[]
            )

        rows = self._amounts.list_precedents(
            item_name=item_name, project_ids=scope, limit=limit
        )
        precedents = [
            AmountPrecedentItem(
                project_id=project_id,
                project_name=project_name,
                document_id=item.document_id,
                document_filename=filename,
                item_name=item.item_name,
                category=item.category,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                amount=item.amount,
                period_from=item.period_from,
                period_to=item.period_to,
                source_quote=item.source_quote,
                decision=item.decision,
            )
            for item, filename, project_id, project_name in rows
        ]

        summary = None
        if precedents:
            prices = [p.unit_price for p in precedents]
            summary = AmountPrecedentSummary(
                count=len(prices),
                min_unit_price=min(prices),
                median_unit_price=median(prices),
                max_unit_price=max(prices),
            )

        logger.info(
            "단가 선례 조회 item=%s 프로젝트=%s 결과=%d건",
            item_name,
            scope,
            len(precedents),
        )
        return AmountPrecedentResponse(
            item_name=item_name,
            searched_project_ids=scope,
            summary=summary,
            precedents=precedents,
        )

    # --- 내부 ---------------------------------------------------------------

    def _resolve_scope(self, user_id: int, current_project_id: int) -> list[int]:
        """찾아볼 프로젝트 = 내가 멤버인 프로젝트 − 현재 프로젝트.

        "과거 유사 사업" 을 "내가 멤버인 다른 프로젝트" 로 읽는다. 의미 검색에서
        정한 것과 같은 읽기다 — 내가 멤버가 아닌 프로젝트는 어떤 경우에도 보이지
        않아야 한다(SRH-001). 현재 프로젝트를 빼는 것이 이 기능의 차이다.

        멤버십을 서비스에서 확인하고 리포지토리에 목록으로 넘긴다. 리포지토리가
        권한을 판단하면 판단 지점이 두 곳이 되어 어긋난다. 조회가 두 번 나가지만
        (멤버십 + 선례) 항상 두 번이라 N+1 이 아니다 — SearchService 와 같은
        방식이고, Spring 의 @BatchSize 와 같은 방향이다.
        """
        member_ids = [
            project.id for project, _member in self._projects.list_for_user(user_id)
        ]
        return sorted(pid for pid in member_ids if pid != current_project_id)
