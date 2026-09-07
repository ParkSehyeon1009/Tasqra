# ① 책임: 검증된 금액 DTO와 분석 메타데이터를 분석 이력 및 PENDING 금액 항목으로 저장한다.
# ② 관계: amount_parser 결과를 받아 AnalysisRepository와 AmountRepository에 위임한다.
# ③ Spring 비교: @Service가 Analysis와 AmountItem saveAll을 조립하며 트랜잭션은 호출자가 연다.

from decimal import Decimal

from app.analyzers.protocol import AnalyzeResult
from app.models.amount import AmountItem
from app.models.document import Analysis
from app.repositories.amount_repository import AmountRepository
from app.repositories.analysis_repository import AnalysisRepository
from app.schemas.amount import AmountExtractionOut

_PENDING = "PENDING"


def _decimal(value: int | float | Decimal | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class AmountWriter:
    """분석 이력과 현재 검토 대기 금액을 같은 외부 트랜잭션에 쌓는다."""

    def __init__(
        self,
        analysis_repository: AnalysisRepository,
        amount_repository: AmountRepository,
    ) -> None:
        self._analysis_repository = analysis_repository
        self._amount_repository = amount_repository

    def write(
        self,
        *,
        document_id: int,
        source_text_revision: int,
        source_ocr_revision: int,
        analyzer_type: str,
        result: AnalyzeResult,
        extraction: AmountExtractionOut,
    ) -> tuple[Analysis, list[AmountItem]]:
        """이전 PENDING만 교체하고 사람이 검토한 행과 분석 이력은 보존한다.

        stated_total은 검증된 Analysis.result_json에만 둔다. PENDING 추출값으로
        기존 승인 항목의 합계 대조 기준(Document.stated_total_amount)을 바꾸지 않는다.
        """
        analysis = self._analysis_repository.create(
            Analysis(
                document_id=document_id,
                analyzer_type=analyzer_type,
                result_json=extraction.model_dump(mode="json"),
                provider=result.provider,
                model_name=result.model_name,
                prompt_version=result.prompt_version,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                latency_ms=result.latency_ms,
                source_text_revision=source_text_revision,
            )
        )

        self._amount_repository.delete_pending_items(document_id)
        rows = [
            AmountItem(
                document_id=document_id,
                analysis_id=analysis.id,
                item_name=item.item_name,
                category=item.category.value if item.category is not None else None,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=_decimal(item.unit_price),
                amount=_decimal(item.amount),
                currency=extraction.currency,
                period_from=item.period_from,
                period_to=item.period_to,
                source_quote=item.source_quote,
                confidence=_decimal(item.confidence),
                reason=item.reason,
                decision=_PENDING,
                decided_by=None,
                decided_at=None,
                source_text_revision=source_ocr_revision,
            )
            for item in extraction.items
        ]
        return analysis, self._amount_repository.add_items(rows)
