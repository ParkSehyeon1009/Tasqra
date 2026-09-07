# 이 파일의 책임: 비동기 AI 분석 작업의 접수·진행·완료·실패 상태와 원자적 저장을 관리한다.
# 다른 파일과의 관계: worker가 호출하며, AnalysisService에 잠긴 Document와 검증된 결과를 전달한다.
# Spring 비교: 큐 작업 수명주기와 트랜잭션 경계를 담당하는 @Service다.

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.analysis_job import AnalysisJob
from app.schemas.document import AnalysisJobResponse, AnalysisResponse

logger = logging.getLogger(__name__)


class AnalysisJobService:
    def __init__(self, db, documents, jobs, analysis):
        self.db, self.documents, self.jobs, self.analysis = db, documents, jobs, analysis

    @staticmethod
    def _same_source(document, job):
        extracted = document.extracted_text if document else None
        return (extracted is not None and extracted.text_version == job.source_text_revision
                and hashlib.sha256(extracted.content.encode("utf-8")).hexdigest() == job.source_text_hash)

    @staticmethod
    def _expire(job):
        if job and job.status in ("PENDING", "RUNNING") and job.expires_at <= datetime.now(timezone.utc):
            AnalysisJobService._fail(job, ErrorCode.AI_TIMEOUT, "분석 작업 시간이 초과되었습니다. 다시 실행해 주세요.")

    @staticmethod
    def _fail(job, code, message=None):
        job.status = "FAILED"
        job.error_code = code.code
        job.error_message = message or code.message
        # 실패 구간을 식별할 수 있도록 마지막 stage는 유지한다.

    def _response(self, job):
        return AnalysisJobResponse(
            job_id=job.id, document_id=job.document_id, status=job.status,
            stage=job.stage, completed_units=job.completed_units, total_units=job.total_units,
            error_code=job.error_code, error_message=job.error_message,
            analyzer_errors=getattr(job, "analyzer_errors", None) or [],
            analyses=[AnalysisResponse.model_validate(row) for row in self.jobs.results(job)],
        )

    def enqueue(self, project_id, document_id, analyzer_types, dispatch):
        types = self.analysis.validate_types(analyzer_types)
        with transactional(self.db):
            document = self.documents.get_by_id_for_update(project_id, document_id)
            if document is None:
                raise BusinessError(ErrorCode.DOCUMENT_NOT_FOUND)
            if document.extracted_text is None:
                raise BusinessError(ErrorCode.NOT_EXTRACTED_YET)
            active = self.jobs.active(document_id)
            self._expire(active)
            if active and active.status in ("PENDING", "RUNNING"):
                if set(active.analyzer_types) != set(types):
                    raise BusinessError(ErrorCode.ANALYSIS_IN_PROGRESS)
                return self._response(active)
            self.db.flush()  # 만료 작업의 부분 unique 인덱스를 먼저 해제한다.
            now = datetime.now(timezone.utc)
            job = self.jobs.add(AnalysisJob(id=str(uuid.uuid4()), project_id=project_id,
                document_id=document_id, source_text_revision=document.extracted_text.text_version,
                source_text_hash=hashlib.sha256(document.extracted_text.content.encode("utf-8")).hexdigest(),
                analyzer_types=types, status="PENDING", stage="대기 중",
                completed_units=0, total_units=0, analysis_ids=[], created_at=now,
                analyzer_errors=[],
                expires_at=now + timedelta(seconds=settings.AI_ANALYSIS_TIMEOUT_SECONDS)))
            job_id = job.id
        # 커밋 후 전달한다. 큐 등록 실패를 성공 응답으로 숨기지 않는다.
        try:
            dispatch(project_id, document_id, job_id)
        except Exception as exc:
            with transactional(self.db):
                job = self.jobs.get(project_id, document_id, job_id, lock=True)
                if job and job.status == "PENDING":
                    self._fail(job, ErrorCode.ANALYSIS_QUEUE_ERROR)
            raise BusinessError(ErrorCode.ANALYSIS_QUEUE_ERROR) from exc
        return self.get(project_id, document_id, job_id)

    def get(self, project_id, document_id, job_id=None):
        with transactional(self.db):
            if job_id is None:
                latest = self.jobs.latest(project_id, document_id)
                if latest is None:
                    return None
                job_id = latest.id
            job = self.jobs.get(project_id, document_id, job_id, lock=True)
            if job is None:
                raise BusinessError(ErrorCode.ANALYSIS_JOB_NOT_FOUND)
            self._expire(job)
            return self._response(job)

    async def run(self, project_id, document_id, job_id, progress):
        # 문서→작업 순서로 잠가 enqueue/완료 사이 잠금 역전을 피한다.
        with transactional(self.db):
            document = self.documents.get_by_id_for_update(project_id, document_id)
            job = self.jobs.get(project_id, document_id, job_id, lock=True)
            self._expire(job)
            if job is None or job.status != "PENDING":
                return  # 중복 전달·완료된 작업을 다시 실행하지 않는다.
            if not self._same_source(document, job):
                self._fail(job, ErrorCode.ANALYSIS_SOURCE_CHANGED)
                return
            content, revision = document.extracted_text.content, job.source_text_revision
            types = list(job.analyzer_types)
            seconds = (job.expires_at - datetime.now(timezone.utc)).total_seconds()
            job.status, job.stage = "RUNNING", "분석 준비"
        try:
            results, analyzer_errors = await asyncio.wait_for(
                self.analysis.analyze_text_isolated(content, types, progress), max(0, seconds))
            with transactional(self.db):
                document = self.documents.get_by_id_for_update(project_id, document_id)
                job = self.jobs.get(project_id, document_id, job_id, lock=True)
                self._expire(job)
                if job is None or job.status != "RUNNING":
                    return
                if not self._same_source(document, job):
                    self._fail(job, ErrorCode.ANALYSIS_SOURCE_CHANGED)
                    return
                if not results:
                    first = analyzer_errors[0] if analyzer_errors else None
                    raise BusinessError(ErrorCode.AI_ANALYZER_FAILED,
                        first["message"] if first else "모든 분석 단계가 실패했습니다.")
                rows = self.analysis.save_results(document, revision, results)
                self.db.flush()
                job.analysis_ids = [row.id for row in rows]
                job.analyzer_errors = analyzer_errors
                job.status = "PARTIAL" if analyzer_errors else "COMPLETED"
                job.stage = "일부 완료" if analyzer_errors else "완료"
                job.completed_units = job.total_units = 1
        except Exception as exc:
            logger.exception("분석 작업 실패 job_id=%s", job_id)
            code = ErrorCode.AI_TIMEOUT if isinstance(exc, asyncio.TimeoutError) else (
                exc.error_code if isinstance(exc, BusinessError) else ErrorCode.AI_ANALYZER_FAILED)
            with transactional(self.db):
                job = self.jobs.get(project_id, document_id, job_id, lock=True)
                if job and job.status in ("PENDING", "RUNNING"):
                    self._fail(job, code, exc.detail if isinstance(exc, BusinessError) else None)
