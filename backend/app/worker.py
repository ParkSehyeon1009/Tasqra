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
    # ExtractionService.process_document 안에 넣지 않고 여기 둔 이유는, 문서
    # 추출이 DOC 영역이라 그쪽 서비스 코드를 건드리지 않으려는 것이다.
    enqueue_build_chunks(project_id, document_id, reason="문서 추출 완료")

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



def enqueue_build_chunks(project_id: int, document_id: int, *, reason: str) -> bool:
    """청킹·임베딩 태스크를 큐에 넣는다. 실패해도 예외를 올리지 않는다.

    부르는 쪽마다 try/except 를 복사하지 않게 하려고 여기 모았다. 지금 두 곳에서
    부른다 — 문서 추출 완료 직후(RAG-01 · RAG-02), OCR 검수 확정 직후(RAG-09).

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
        build_chunks_task.delay(project_id, document_id)
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
