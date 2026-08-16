from celery import Celery

from app.core.config import settings
from app.db.session import SessionLocal

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
