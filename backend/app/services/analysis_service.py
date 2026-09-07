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

# ⚠️ **"features" 는 일부러 빠져 있다.** 레지스트리에는 등록돼 있으므로
#   types=["features"] 로 부르면 돌지만 기본으로는 돌지 않는다.
#
#   같은 목적(문서에서 할 일을 뽑아 태스크 제안으로)을 가진 분석기가 둘이다:
#
#     action_task  후보를 파이썬 규칙으로 찾고(action_candidate_finder) 모델은
#                  **그중에서 고른다.** 없는 것을 만들 수 없다. 제안 저장·승인
#                  흐름(task_suggestions)이 여기에 붙어 있다 -> **기본값**
#     features     모델이 과업을 **생성한다.** 사업 범위를 분해하는 쪽에 가깝다
#                  (「현황 및 수요분석」·「통계 대시보드 개발」) -> 필요할 때만
#
#   ⚠️ features 를 기본에서 뺀 이유는 둘이다. (1) 둘 다 켜면 문서마다 서로 다른
#     태스크 목록이 두 개 나온다. (2) 생성 방식이라 **지어낼 수 있다** — 실측
#     22건 중 2건에서 「공고서 작성·개찰·자격 등록」같은 발주기관의 입찰 절차를
#     과업으로 뽑았다. 구간 단위 재학습으로도 못 고쳤다(2026-09-07 패치노트).
#     action_task 의 후보 찾기는 그 부류를 규칙으로 제외한다(_EXCLUDE).
#
#   ⚠️ 비용도 다르다. features 는 구간마다 호출해 문서당 중앙 8회·4초,
#     긴 문서는 48회·114초다.
DEFAULT_ANALYZER_TYPES = ["summary", "category", "decision", "schedule", "action_task"]

# 🔑 액션 태스크를 뽑을 문서 유형. **이 밖에서는 분석기를 아예 부르지 않는다.**
#
# 왜 유형으로 가르나 — 실측(2026-09-07, 실제 문서 3건)에서 유형이 결과를 갈랐다:
#
#     재공고서(RFP)      제안 19건 중 쓸 만한 것 1건
#     제안요청서(RFP)    제안 10건 중 쓸 만한 것 **0건**
#     과업지시서(CONTRACT) 제안  9건 중 쓸 만한 것 **9건**
#
# 우연이 아니라 구조다. action_candidate_finder 는 「제출·작성·등록 + 하여야/까지」
# 를 찾는데, **공공 입찰 문서에서 그 어미가 붙는 문장은 거의 전부 입찰 절차다**
# (입찰보증금 납부·공동수급협정서 제출·제안서 제본 규격…). 반면 진짜 과업은
# 「고정수리센터를 운영한다」처럼 범위 서술이라 의무 어미가 없다.
# 그래서 후보 찾기가 정확할수록 절차만 골라온다 — 규칙을 손봐서 될 문제가 아니다.
#
# 노이즈의 크기가 문제다. 두 RFP 문서에서 29건 중 1건만 진짜였다. 승인 화면에
# 그것이 쌓이면 사람이 기능 자체를 안 믿게 된다.
#
# ⚠️ **표본 3건이다.** 메커니즘은 설명되지만 확정은 아니다. 되돌리려면 이 집합을
#   넓히거나 비우면 된다(비우면 전부 건너뛴다는 뜻이 아니라, 아래 _skip_reason 이
#   category 를 모를 때 돌리는 쪽으로 떨어지므로 주의).
#
# ⚠️ RFP·PROPOSAL 에서 「수행할 과업」을 뽑는 것은 features 분석기의 몫이다.
#   같은 제안요청서에서 features 는 「교통편 제공·숙식 제공·견학장소 예약 및 섭외」
#   를 정확히 찾았다. 다만 task_suggestions 에 쓰는 경로가 아직 없다.
ACTION_TASK_CATEGORIES = frozenset({"CONTRACT", "CONTRACT_CHANGE"})


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

    @staticmethod
    def _skip_reason(name, results):
        """이 분석기를 건너뛸 이유가 있으면 문장으로, 없으면 None.

        ⚠️ **분석기 사이에 순서 의존이 생기는 자리다.** category 결과를 보고
          action_task 를 켤지 정하므로, DEFAULT_ANALYZER_TYPES 에서 category 가
          action_task 보다 **앞에** 있어야 한다. 순서를 바꾸면 조용히 안 걸러진다
          (테스트로 잠가 뒀다).

        ⚠️ **모르면 거르지 않는다.** category 를 안 돌렸거나 결과가 없으면 그냥
          돌린다. 분류가 없다는 이유로 기능이 사라지면 사용자는 원인을 알 수 없다.
        """
        if name != "action_task":
            return None
        category = next((r.result.get("category") for n, r in results if n == "category"),
                        None)
        if category is None or category in ACTION_TASK_CATEGORIES:
            return None
        return f"{category} 문서에서는 액션 태스크를 뽑지 않습니다"

    @staticmethod
    def _skipped_result(analyzer, reason):
        """건너뛴 것도 **결과로 남긴다.**

        ⚠️ 그냥 지나가면 「제안이 왜 없나」에 답할 수 없다. 분류가 틀려서
          건너뛴 경우가 특히 그렇다 — 화면에서 원인을 보여줄 수 있어야 한다.
        """
        from app.analyzers.protocol import AnalyzeResult

        return AnalyzeResult(
            result={"task_suggestions": [], "skipped": reason,
                    "candidate_count": 0, "selected_count": 0, "call_count": 0},
            # 모델을 부르지 않았다. 부른 척하지 않는다.
            provider="skipped", model_name="-",
            prompt_version=getattr(analyzer, "prompt_version", "-"), latency_ms=0)

    async def analyze_text(self, content, types, progress=None):
        # 로컬 GPU에 요약·분류 요청을 동시에 쌓지 않는다.
        results = []
        for name in types:
            analyzer = self._analyzer_registry[name]
            reason = self._skip_reason(name, results)
            if reason:
                results.append((name, self._skipped_result(analyzer, reason)))
                continue
            result = await analyzer.analyze(content, progress=progress)
            results.append((name, result))
        return results

    async def analyze_text_isolated(self, content, types, progress=None):
        """분석기 하나의 국소 오류가 다른 분석 결과를 폐기하지 않게 한다."""
        results, errors = [], []
        for name in types:
            analyzer = self._analyzer_registry[name]
            reason = self._skip_reason(name, results)
            if reason:
                results.append((name, self._skipped_result(analyzer, reason)))
                continue
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
