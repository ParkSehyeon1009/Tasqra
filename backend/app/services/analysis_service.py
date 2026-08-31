from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.document import Analysis

DEFAULT_ANALYZER_TYPES = ["summary", "category"]


class AnalysisService:
    def __init__(self, db, document_repository, analysis_repository, analyzer_registry):
        self._db = db
        self._document_repository = document_repository
        self._analysis_repository = analysis_repository
        self._analyzer_registry = analyzer_registry

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

    def save_results(self, document_id, revision, results):
        return [self._analysis_repository.create(Analysis(
            document_id=document_id, analyzer_type=name, result_json=result.result,
            provider=result.provider, model_name=result.model_name,
            prompt_version=result.prompt_version, tokens_in=result.tokens_in,
            tokens_out=result.tokens_out, latency_ms=result.latency_ms,
            source_text_revision=revision,
        )) for name, result in results]

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
            return self.save_results(document_id, revision, results)
