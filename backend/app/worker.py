import logging

from celery import Celery

from app.core.config import settings
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
)


@celery_app.task(
    bind=True,
    name="documents.extract",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 2},
)
def extract_document_task(self, project_id: int, document_id: int) -> int:
    # Imports are delayed so Celery can initialize without loading the OCR model.
    from app.dependencies import get_extractor_registry
    from app.repositories.document_repository import DocumentRepository
    from app.services.extraction_service import ExtractionService

    with SessionLocal() as db:
        service = ExtractionService(db, DocumentRepository(db), get_extractor_registry())
        service.process_document(project_id, document_id)

    # 추출이 끝나면 청킹·임베딩을 이어서 큐에 넣는다 (RAG-01 · RAG-02).
    #
    # ExtractionService.process_document 안에 넣지 않고 여기 둔 이유가 두 개다.
    #   1. 문서 추출은 DOC 영역이라 그쪽 서비스 코드를 건드리지 않는다.
    #   2. 이 태스크에 autoretry_for=(Exception,) 이 걸려 있다. 큐 넣기가 실패해
    #      예외가 올라가면 OCR 추출 전체가 다시 돈다 — 가장 비싼 작업이다.
    #      그래서 try/except 로 감싸 추출 결과를 지킨다.
    #
    # 실패해도 청크는 나중에 복구할 수 있다. chunks.build 를 직접 호출하거나,
    # ChunkRepository.stale_document_ids() 로 빠진 문서를 찾아 다시 돌린다.
    try:
        build_chunks_task.delay(project_id, document_id)
    except Exception:  # noqa: BLE001 - 추출 성공을 되돌리지 않는 것이 우선이다
        logger.exception(
            "청킹 큐 등록에 실패했다. 추출은 성공했다. "
            "document_id=%s project_id=%s — chunks.build 를 직접 실행해 복구한다",
            document_id,
            project_id,
        )

    return document_id


@celery_app.task(
    bind=True,
    name="chunks.build",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={"max_retries": 2},
)
def build_chunks_task(self, project_id: int, document_id: int) -> int:
    """문서 하나를 청킹하고 임베딩해 document_chunks 에 넣는다 (RAG-01 · RAG-02).

    documents.extract 태스크와 일부러 분리해 뒀다. 문서 추출 파이프라인은
    DOC 영역이라 그쪽을 건드리지 않으려는 것이고, 이렇게 두면 세 가지가 된다.
      (1) 추출을 다시 돌리지 않고 청킹만 다시 돌릴 수 있다 (규칙을 바꿀 때)
      (2) OCR 검수를 확정한 뒤 재임베딩(RAG-09)에 같은 태스크를 재사용한다
      (3) 추출 파이프라인에 연결할 때 아래 한 줄만 넣으면 된다
            build_chunks_task.delay(project_id, document_id)

    임포트를 함수 안에서 하는 이유는 extract_document_task 와 같다 — Celery 가
    기동할 때 무거운 것을 끌어오지 않게 한다. 임베딩 구현이 나중에 실제 모델을
    쓰게 되면 이 지연 임포트가 특히 중요해진다.
    """
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
