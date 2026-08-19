# =============================================================================
# 이 파일의 책임: analyses 테이블에 대한 CRUD를 담당한다. 하나의 document에
#   여러 analyzer_type(summary/category)의 분석 결과가 1:N으로 쌓이는 구조를
#   그대로 반영한다 (재분석 시 기존 행을 덮어쓰지 않고 새 행을 추가한다).
# 다른 파일과의 관계: dependencies.py의 get_analysis_repository()가 주입한다.
#   analysis_service.py(담당자 B)가 POST /documents/{id}/analyze 처리 시 사용.
# Spring 비교: Spring Data JPA의 AnalysisRepository(JpaRepository<Analysis, Long>)와
#   동일한 위치. findByDocumentId 같은 메서드를 여기서는 명시적으로 작성한다.
# =============================================================================

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.document import Analysis


class AnalysisRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, analysis: Analysis) -> Analysis:
        self._db.add(analysis)
        self._db.flush()
        return analysis

    def list_by_document(self, document_id: int) -> list[Analysis]:
        return (
            self._db.query(Analysis)
            .filter(Analysis.document_id == document_id)
            .order_by(Analysis.created_at.desc())
            .all()
        )

    def get_latest_by_type(self, document_id: int, analyzer_type: str) -> Analysis | None:
        return (
            self._db.query(Analysis)
            .filter(
                Analysis.document_id == document_id,
                Analysis.analyzer_type == analyzer_type,
            )
            .order_by(Analysis.created_at.desc())
            .first()
        )

    def get_latest_by_types(
        self,
        document_ids: list[int],
        analyzer_types: list[str],
    ) -> dict[tuple[int, str], Analysis]:
        """문서 목록에 필요한 유형별 최신 분석 결과를 한 번에 조회한다."""
        if not document_ids or not analyzer_types:
            return {}

        ranked = (
            self._db.query(
                Analysis.id.label("analysis_id"),
                func.row_number()
                .over(
                    partition_by=(Analysis.document_id, Analysis.analyzer_type),
                    order_by=(Analysis.created_at.desc(), Analysis.id.desc()),
                )
                .label("position"),
            )
            .filter(
                Analysis.document_id.in_(document_ids),
                Analysis.analyzer_type.in_(analyzer_types),
            )
            .subquery()
        )
        analyses = (
            self._db.query(Analysis)
            .join(ranked, ranked.c.analysis_id == Analysis.id)
            .filter(ranked.c.position == 1)
            .all()
        )

        return {
            (analysis.document_id, analysis.analyzer_type): analysis
            for analysis in analyses
        }
