import logging

from celery import Celery

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.middleware import bind_request_id
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

celery_app = Celery(
    "tasqra",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    # Celery 가 루트 로거를 가로채지 않게 한다(기본값은 True 다). 가로채면 아래
    # setup_logging() 이 붙인 포맷터가 밀려나 request_id 가 사라진다.
    worker_hijack_root_logger=False,
)

# 워커 프로세스의 로깅을 여기서 설정한다 (SYS-003-1).
#
# **여기서 부르지 않으면 값을 넘겨도 아무것도 안 보인다.** 워커는
# `celery -A app.worker.celery_app worker` 로 뜨고 app.main 을 절대 불러오지
# 않는다. 그래서 setup_logging() 이 main.py 에만 있으면 워커 로그에는
# [request_id=...] 포맷터 자체가 붙지 않는다 — 값이 "-" 로 찍히는 게 아니라
# 아예 없다.
#
# API 프로세스에서도 이 줄이 실행된다(main.py 가 라우터를 import 하는 사슬로
# 이 모듈이 끌려온다). setup_logging() 이 멱등이라 두 번째는 아무 일도 하지 않는다.
setup_logging()


@celery_app.task(
    bind=True,
    name="documents.extract",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 2},
)
def extract_document_task(self, project_id: int, document_id: int, request_id: str = "-") -> int:
    # request_id 를 **기본값 있는 키워드 인자**로 받는다. 이유가 둘이고 두 번째가
    # 실제로 사고 나는 지점이다 (SYS-003-1).
    #
    #   (1) 이 태스크를 부르는 곳이 셋이라 한 곳을 미뤄도 안 깨진다
    #   (2) **배포 순간 큐에 남아 있던 메시지**는 인자 2개로 들어온다. 필수 인자로
    #       만들면 그 태스크들이 전부 TypeError 로 죽는다 — 그 시점에 올라온
    #       문서가 조용히 처리되지 않는다. 사용자는 업로드가 됐다고 본다.
    bind_request_id(request_id)

    # Imports are delayed so Celery can initialize without loading the OCR model.
    from app.dependencies import get_extractor_registry
    from app.repositories.document_repository import DocumentRepository
    from app.services.extraction_service import ExtractionService

    with SessionLocal() as db:
        service = ExtractionService(db, DocumentRepository(db), get_extractor_registry())
        service.process_document(project_id, document_id)

    # 추출이 끝나면 청킹·임베딩을 이어서 큐에 넣는다 (RAG-001-1 · RAG-001-2).
    #
    # ExtractionService.process_document 안에 넣지 않고 여기 둔 이유는, 문서
    # 추출이 DOC 영역이라 그쪽 서비스 코드를 건드리지 않으려는 것이다.
    #
    # request_id 를 그대로 넘겨 사슬을 잇는다. 여기서 빠뜨리면 "업로드는 됐는데
    # 검색이 안 된다" 는 신고를 받았을 때 청킹 로그를 찾을 수 없다 — 추출까지는
    # 이어지고 그다음이 끊긴다.
    enqueue_build_chunks(project_id, document_id, reason="문서 추출 완료", request_id=request_id)

    return document_id


@celery_app.task(
    bind=True,
    name="chunks.build",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 2},
)
def build_chunks_task(self, project_id: int, document_id: int, request_id: str = "-") -> int:
    """문서 하나를 청킹하고 임베딩해 document_chunks 에 넣는다 (RAG-001-1 · RAG-001-2).

    documents.extract 태스크와 일부러 분리해 뒀다. 문서 추출 파이프라인은
    DOC 영역이라 그쪽을 건드리지 않으려는 것이고, 이렇게 두면 세 가지가 된다.
      (1) 추출을 다시 돌리지 않고 청킹만 다시 돌릴 수 있다 (규칙을 바꿀 때)
      (2) OCR 검수를 확정한 뒤 재임베딩(RAG-001-3)에 같은 태스크를 재사용한다
      (3) 추출 파이프라인에 연결할 때 아래 한 줄만 넣으면 된다
            build_chunks_task.delay(project_id, document_id)

    임포트를 함수 안에서 하는 이유는 extract_document_task 와 같다 — Celery 가
    기동할 때 무거운 것을 끌어오지 않게 한다. 임베딩 구현이 나중에 실제 모델을
    쓰게 되면 이 지연 임포트가 특히 중요해진다.
    """
    bind_request_id(request_id)

    from app.dependencies import get_embedding_client
    from app.repositories.chunk_repository import ChunkRepository
    from app.services.chunking_service import ChunkingService

    with SessionLocal() as db:
        service = ChunkingService(
            db=db,
            chunk_repository=ChunkRepository(db),
            embedding_client=get_embedding_client(),
        )
        return service.rebuild_for_document(project_id, document_id)



def enqueue_build_chunks(project_id: int, document_id: int, *, reason: str, request_id: str = "-") -> bool:
    """청킹·임베딩 태스크를 큐에 넣는다. 실패해도 예외를 올리지 않는다.

    부르는 쪽마다 try/except 를 복사하지 않게 하려고 여기 모았다. 지금 두 곳에서
    부른다 — 문서 추출 완료 직후(RAG-001-1 · RAG-001-2), OCR 검수 확정 직후(RAG-001-3).

    실패를 삼키는 것이 핵심이고, 두 곳 모두 같은 이유다. **이미 성공해서 커밋된
    작업을 큐 등록 실패 때문에 되돌리면 안 된다.**

      · 문서 추출 완료 — extract_document_task 에 autoretry_for=(Exception,) 이
        걸려 있다. 여기서 예외가 올라가면 가장 비싼 OCR 추출이 전부 다시 돈다.
      · OCR 검수 확정 — 검수는 이미 커밋됐다. 여기서 예외를 올려 503 을 주면
        사용자는 "검수 완료가 실패했다"고 읽고 다시 누르는데, 실제로는 이미
        완료돼 있다. 사용자에게 거짓을 말하는 셈이다.

    그래서 로그만 남기고 False 를 돌려준다. 놓친 문서는 나중에 찾을 수 있다 —
    ChunkRepository.stale_document_ids() 가 청크의 text_version 이 본문의
    text_version 보다 작은 문서를 준다. 그것이 그 메서드의 용도다.

    Spring 비교: 성공한 트랜잭션 뒤에 붙는 후속 작업이라
    @TransactionalEventListener(phase = AFTER_COMMIT) 안에서 메시지를 보내는 것과
    같은 자리다. 그 자리에서 예외를 던지면 앞의 커밋을 되돌리지 못하면서 응답만
    깨지는 것도 똑같다.
    """
    try:
        build_chunks_task.delay(project_id, document_id, request_id=request_id)
        return True
    except Exception:  # noqa: BLE001 - 이미 성공한 작업을 지키는 것이 우선이다
        logger.exception(
            "청킹 큐 등록에 실패했다 (%s). project_id=%s document_id=%s — "
            "chunks.build 를 직접 실행하거나 stale_document_ids() 로 찾아 복구한다",
            reason,
            project_id,
            document_id,
        )
        return False


@celery_app.task(name="documents.analyze", time_limit=settings.AI_ANALYSIS_TIMEOUT_SECONDS + 30)
def analyze_document_task(project_id: int, document_id: int, job_id: str, request_id: str = "-"):
    import asyncio
    from app.analyzers.summary_analyzer import SummaryAnalyzer
    from app.analyzers.category_analyzer import CategoryAnalyzer
    from app.repositories.analysis_job_repository import AnalysisJobRepository
    from app.repositories.analysis_repository import AnalysisRepository
    from app.repositories.document_repository import DocumentRepository
    from app.services.analysis_service import AnalysisService
    from app.services.analysis_job_service import AnalysisJobService
    from app.core.transaction import transactional

    bind_request_id(request_id)

    def progress(stage, done, total):
        # 짧은 별도 트랜잭션. 모델 응답 대기 중 DB 연결을 잡지 않는다.
        with SessionLocal() as db:
            with transactional(db):
                AnalysisJobRepository(db).progress(job_id, stage, done, total)

    async def run():
        # asyncio.run마다 루프가 달라지므로 캐시된 AsyncOpenAI 클라이언트를 재사용하지 않는다.
        from contextlib import AsyncExitStack
        from app.ai.fake_client import FakeAIClient
        from app.ai.local_client import LocalAIClient
        from app.ai.openai_client import OpenAIClient
        from app.analyzers.extraction_analyzer import DecisionAnalyzer
        from app.analyzers.schedule_analyzer import ScheduleAnalyzer
        from app.repositories.decision_schedule_repository import DecisionScheduleRepository
        from app.services.decision_schedule_writer import DecisionScheduleWriter

        def make_client(model):
            if settings.USE_FAKE_AI:
                return FakeAIClient()
            client_type = LocalAIClient if settings.AI_PROVIDER.lower() == "local" else OpenAIClient
            return client_type(settings, model or None)

        async with AsyncExitStack() as stack:
            # API와 동일하게 개별 모델을 선택하고, 비어 있으면 AI_MODEL을 사용한다.
            summary_client = make_client(settings.AI_MODEL_SUMMARY)
            if hasattr(summary_client, "aclose"):
                stack.push_async_callback(summary_client.aclose)
            category_client = make_client(settings.AI_MODEL_CATEGORY)
            if hasattr(category_client, "aclose"):
                stack.push_async_callback(category_client.aclose)
            decision_client = make_client(settings.AI_MODEL_DECISION)
            if hasattr(decision_client, "aclose"):
                stack.push_async_callback(decision_client.aclose)
            schedule_client = make_client(settings.AI_MODEL_SCHEDULE)
            if hasattr(schedule_client, "aclose"):
                stack.push_async_callback(schedule_client.aclose)
            with SessionLocal() as db:
                documents = DocumentRepository(db)
                analysis_repository = AnalysisRepository(db)
                writer = DecisionScheduleWriter(
                    analysis_repository, DecisionScheduleRepository(db))
                analysis = AnalysisService(db, documents, analysis_repository, {
                    "summary": SummaryAnalyzer(summary_client),
                    "category": CategoryAnalyzer(category_client),
                    "decision": DecisionAnalyzer(decision_client),
                    "schedule": ScheduleAnalyzer(schedule_client),
                }, writer)
                service = AnalysisJobService(db, documents, AnalysisJobRepository(db), analysis)
                await service.run(project_id, document_id, job_id, progress)
    asyncio.run(run())
    return job_id
