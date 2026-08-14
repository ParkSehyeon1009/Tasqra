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
