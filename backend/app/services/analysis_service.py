# 이 파일의 책임: AI 분석 결과를 이력으로 저장하고 자동 분류 문서의 유형을 갱신한다.
# 다른 파일과의 관계: AnalysisJobService가 잠근 Document와 분석 결과를 넘기면 같은 트랜잭션에 반영한다.
# Spring 비교: 분석 결과 저장과 자동 분류 정책을 묶는 @Service 계층이다.

import json

from pydantic import ValidationError

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.document import Analysis
from app.models.enums import DocumentTypeSource
from app.schemas.extraction import DecisionExtractionList, ScheduleItemExtractionList, TaskSuggestionExtractionList

DEFAULT_ANALYZER_TYPES = ["summary", "category", "decision", "schedule", "action_task"]


class AnalysisService:
    def __init__(self, db, document_repository, analysis_repository, analyzer_registry,
                 decision_schedule_writer, task_suggestion_writer):
        self._db = db
        self._document_repository = document_repository
        self._analysis_repository = analysis_repository
        self._analyzer_registry = analyzer_registry
        self._decision_schedule_writer = decision_schedule_writer
        self._task_suggestion_writer = task_suggestion_writer

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

    async def analyze_text_isolated(self, content, types, progress=None):
        """분석기 하나의 국소 오류가 다른 분석 결과를 폐기하지 않게 한다."""
        results, errors = [], []
        for name in types:
            analyzer = self._analyzer_registry[name]
            try:
                result = await analyzer.analyze(content, progress=progress)
            except BusinessError as exc:
                errors.append({"analyzer": name, "code": exc.error_code.code,
                    "message": exc.detail or exc.error_code.message})
                continue
            results.append((name, result))
            failed_units = result.result.get("failed_groups") or result.result.get("failed_chunks")
            if failed_units:
                errors.append({"analyzer": name, "code": "AI_PARTIAL_RESULT",
                    "message": f"일부 구간을 처리하지 못했습니다: {failed_units}"})
        return results, errors

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
        rows = []
        for name, result in results:
            if "decisions" in result.result:
                # 분석기가 model_dump(mode="json")로 날짜·Enum을 문자열로
                # 넘긴다. strict DTO에 파이썬 dict를 바로 넣지 말고 JSON 경계에서
                # 다시 검증해 서비스가 받은 계약을 유지한다.
                try:
                    items = DecisionExtractionList.model_validate_json(
                        json.dumps(result.result["decisions"])).root
                except (TypeError, ValidationError) as exc:
                    raise BusinessError(ErrorCode.AI_INVALID_RESPONSE) from exc
                analysis, _ = self._decision_schedule_writer.write_decisions(
                    project_id=document.project_id, document_id=document.id,
                    source_text_revision=revision,
                    source_ocr_revision=document.ocr_revision, analyzer_type=name,
                    result=result, extractions=items)
                rows.append(analysis)
                continue
            if "schedule_items" in result.result:
                try:
                    items = ScheduleItemExtractionList.model_validate_json(
                        json.dumps(result.result["schedule_items"])).root
                except (TypeError, ValidationError) as exc:
                    raise BusinessError(ErrorCode.AI_INVALID_RESPONSE) from exc
                analysis, _ = self._decision_schedule_writer.write_schedule_items(
                    project_id=document.project_id, document_id=document.id,
                    source_text_revision=revision,
                    source_ocr_revision=document.ocr_revision, analyzer_type=name,
                    result=result, extractions=items)
                rows.append(analysis)
                continue
            if "task_suggestions" in result.result:
                try:
                    items = TaskSuggestionExtractionList.model_validate_json(
                        json.dumps(result.result["task_suggestions"])).root
                except (TypeError, ValidationError) as exc:
                    raise BusinessError(ErrorCode.AI_INVALID_RESPONSE) from exc
                analysis, _ = self._task_suggestion_writer.write(
                    project_id=document.project_id, document_id=document.id,
                    source_text_revision=revision, analyzer_type=name,
                    result=result, extractions=items)
                rows.append(analysis)
                continue
            rows.append(self._analysis_repository.create(Analysis(
                document_id=document.id, analyzer_type=name, result_json=result.result,
                provider=result.provider, model_name=result.model_name,
                prompt_version=result.prompt_version, tokens_in=result.tokens_in,
                tokens_out=result.tokens_out, latency_ms=result.latency_ms,
                source_text_revision=revision,
            )))
        return rows

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
