# ① 책임: 검증된 결정사항·일정 DTO와 분석 메타데이터를 하나의 분석 이력 및 PENDING 제안으로 저장한다.
# ② 관계: extraction_parser.py의 결과를 받아 AnalysisRepository와 DecisionScheduleRepository에 위임한다.
# ③ Spring 비교: @Service가 Analysis 저장과 두 JpaRepository.saveAll()을 조립하며 트랜잭션은 호출자가 연다.

from decimal import Decimal

from app.analyzers.protocol import AnalyzeResult
from app.models.decision import Decision
from app.models.document import Analysis
from app.models.schedule import ScheduleItem
from app.repositories.analysis_repository import AnalysisRepository
from app.repositories.decision_schedule_repository import DecisionScheduleRepository
from app.schemas.extraction import DecisionExtraction, ScheduleItemExtraction

_PENDING = "PENDING"


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class DecisionScheduleWriter:
    """분석 이력과 그 분석에서 나온 제안들을 같은 외부 트랜잭션에 쌓는다."""

    def __init__(
        self,
        analysis_repository: AnalysisRepository,
        decision_schedule_repository: DecisionScheduleRepository,
    ) -> None:
        self._analysis_repository = analysis_repository
        self._decision_schedule_repository = decision_schedule_repository

    def write_decisions(
        self,
        *,
        project_id: int,
        document_id: int,
        source_text_revision: int,
        source_ocr_revision: int,
        analyzer_type: str,
        result: AnalyzeResult,
        extractions: list[DecisionExtraction],
    ) -> tuple[Analysis, list[Decision]]:
        analysis = self._create_analysis(
            document_id=document_id,
            source_text_revision=source_text_revision,
            analyzer_type=analyzer_type,
            result=result,
        )
        self._decision_schedule_repository.delete_pending_decisions(
            project_id, document_id
        )
        rows = [
            Decision(
                project_id=project_id,
                document_id=document_id,
                analysis_id=analysis.id,
                title=item.title,
                content=item.content,
                evidence_text=item.evidence_text,
                status=item.status.value,
                decided_on=item.decided_on,
                confidence=_decimal(item.confidence),
                reason=item.reason,
                decision=_PENDING,
                source_text_revision=source_ocr_revision,
            )
            for item in extractions
        ]
        return analysis, self._decision_schedule_repository.add_decisions(rows)

    def write_schedule_items(
        self,
        *,
        project_id: int,
        document_id: int,
        source_text_revision: int,
        source_ocr_revision: int,
        analyzer_type: str,
        result: AnalyzeResult,
        extractions: list[ScheduleItemExtraction],
    ) -> tuple[Analysis, list[ScheduleItem]]:
        analysis = self._create_analysis(
            document_id=document_id,
            source_text_revision=source_text_revision,
            analyzer_type=analyzer_type,
            result=result,
        )
        self._decision_schedule_repository.delete_pending_schedule_items(
            project_id, document_id
        )
        rows = [
            ScheduleItem(
                project_id=project_id,
                document_id=document_id,
                analysis_id=analysis.id,
                title=item.title,
                evidence_text=item.evidence_text,
                kind=item.kind.value,
                starts_on=item.starts_on,
                ends_on=item.ends_on,
                confidence=_decimal(item.confidence),
                reason=item.reason,
                decision=_PENDING,
                source_text_revision=source_ocr_revision,
            )
            for item in extractions
        ]
        return analysis, self._decision_schedule_repository.add_schedule_items(rows)

    def _create_analysis(
        self,
        *,
        document_id: int,
        source_text_revision: int,
        analyzer_type: str,
        result: AnalyzeResult,
    ) -> Analysis:
        return self._analysis_repository.create(
            Analysis(
                document_id=document_id,
                analyzer_type=analyzer_type,
                result_json=result.result,
                provider=result.provider,
                model_name=result.model_name,
                prompt_version=result.prompt_version,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                latency_ms=result.latency_ms,
                source_text_revision=source_text_revision,
            )
        )
