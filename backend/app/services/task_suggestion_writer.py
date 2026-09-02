from decimal import Decimal

from app.models.document import Analysis
from app.models.task_suggestion import TaskSuggestion


class TaskSuggestionWriter:
    def __init__(self, analyses, suggestions):
        self._analyses = analyses
        self._suggestions = suggestions

    def write(self, *, project_id, document_id, source_text_revision,
              analyzer_type, result, extractions):
        # 재분석이 목록을 계속 불리지 않게 미검토 후보는 최신 결과로 교체한다.
        # 이미 승인·수정·거절한 기록과 만들어진 태스크는 보존한다.
        self._suggestions.delete_pending(project_id, document_id)
        analysis = self._analyses.create(Analysis(
            document_id=document_id, analyzer_type=analyzer_type,
            result_json=result.result, provider=result.provider,
            model_name=result.model_name, prompt_version=result.prompt_version,
            tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            latency_ms=result.latency_ms,
            source_text_revision=source_text_revision))
        rows = [TaskSuggestion(project_id=project_id, document_id=document_id,
            analysis_id=analysis.id, title=item.title,
            description=item.description, due_on=item.due_on, actor=item.actor,
            evidence_text=item.evidence_text,
            confidence=None if item.confidence is None else Decimal(str(item.confidence)),
            quality_score=Decimal(str(item.quality_score)), reason=item.reason,
            decision="PENDING", source_text_revision=source_text_revision)
            for item in extractions]
        return analysis, self._suggestions.add_all(rows)
