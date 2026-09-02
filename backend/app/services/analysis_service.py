# 이 파일의 책임: AI 분석 결과를 이력으로 저장하고 자동 분류 문서의 유형을 갱신한다.
# 다른 파일과의 관계: AnalysisJobService가 잠근 Document와 분석 결과를 넘기면 같은 트랜잭션에 반영한다.
# Spring 비교: 분석 결과 저장과 자동 분류 정책을 묶는 @Service 계층이다.

import json

from app.analyzers.extraction_parser import (
    parse_decision_extractions,
    parse_schedule_item_extractions,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.document import Analysis
from app.models.enums import DocumentTypeSource
from app.services.decision_schedule_writer import DecisionScheduleWriter

DEFAULT_ANALYZER_TYPES = ["summary", "category", "decision", "schedule"]


class AnalysisService:
    def __init__(
        self,
        db,
        document_repository,
        analysis_repository,
        analyzer_registry,
        decision_schedule_writer: DecisionScheduleWriter | None = None,
    ):
        self._db = db
        self._document_repository = document_repository
        self._analysis_repository = analysis_repository
        self._analyzer_registry = analyzer_registry
        self._decision_schedule_writer = decision_schedule_writer

    def validate_types(self, analyzer_types):
        types = list(dict.fromkeys(analyzer_types or DEFAULT_ANALYZER_TYPES))
        if any(name not in self._analyzer_registry for name in types):
            raise BusinessError(ErrorCode.ANALYZER_NOT_FOUND)
        return types

    async def analyze_text(self, content, types, progress=None):
        # 로컬 GPU에 요약·분류 요청을 동시에 쌓지 않는다.
        results = []
        for name in types:
            analyzer = self._analyzer_registry[name]
            result = await analyzer.analyze(content, progress=progress)
            results.append((name, result))
        return results

    @staticmethod
    def _apply_ai_document_type(document, results):
        category_result = next((result for name, result in results if name == "category"), None)
        if category_result is None:
            return
        source = document.document_type_source
        should_fill = document.document_type is None and source is None
        should_refresh = source == DocumentTypeSource.AI.value
        if not (should_fill or should_refresh):
            return
        category = category_result.result.get("category")
        if category is None:
            return
        document.document_type = category
        document.document_type_source = DocumentTypeSource.AI.value

    def save_results(self, document, revision, results):
        self._apply_ai_document_type(document, results)
        saved = []
        for name, result in results:
            if name == "decision":
                writer = self._require_decision_schedule_writer()
                extractions = parse_decision_extractions(
                    json.dumps(result.result.get("decisions", []), ensure_ascii=False)
                )
                analysis, _ = writer.write_decisions(
                    project_id=document.project_id,
                    document_id=document.id,
                    source_text_revision=revision,
                    source_ocr_revision=document.ocr_revision,
                    analyzer_type=name,
                    result=result,
                    extractions=extractions,
                )
            elif name == "schedule":
                writer = self._require_decision_schedule_writer()
                extractions = parse_schedule_item_extractions(
                    json.dumps(result.result.get("schedule_items", []), ensure_ascii=False)
                )
                analysis, _ = writer.write_schedule_items(
                    project_id=document.project_id,
                    document_id=document.id,
                    source_text_revision=revision,
                    source_ocr_revision=document.ocr_revision,
                    analyzer_type=name,
                    result=result,
                    extractions=extractions,
                )
            else:
                analysis = self._analysis_repository.create(Analysis(
                    document_id=document.id, analyzer_type=name, result_json=result.result,
                    provider=result.provider, model_name=result.model_name,
                    prompt_version=result.prompt_version, tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out, latency_ms=result.latency_ms,
                    source_text_revision=revision,
                ))
            saved.append(analysis)
        return saved

    def _require_decision_schedule_writer(self) -> DecisionScheduleWriter:
        if self._decision_schedule_writer is None:
            raise RuntimeError("결정·일정 분석 결과 저장기가 연결되지 않았습니다.")
        return self._decision_schedule_writer

    async def analyze_document(self, project_id, document_id, analyzer_types):
        """직접 호출용. HTTP 경로는 AnalysisJobService가 워커에 등록한다."""
        types = self.validate_types(analyzer_types)
        document = self._document_repository.get_by_id(project_id, document_id)
        if document is None:
            raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
        if document.extracted_text is None:
            raise BusinessError(ErrorCode.NOT_EXTRACTED_YET)
        content = document.extracted_text.content
        revision = document.extracted_text.text_version
        self._db.rollback()  # 네트워크 호출 중 읽기 트랜잭션을 유지하지 않는다.
        results = await self.analyze_text(content, types)
        with transactional(self._db):
            document = self._document_repository.get_by_id_for_update(project_id, document_id)
            if (document is None or document.extracted_text is None
                or document.extracted_text.text_version != revision or document.extracted_text.content != content):
                raise BusinessError(ErrorCode.ANALYSIS_SOURCE_CHANGED)
            return self.save_results(document, revision, results)
