from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette import status

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.middleware import get_request_id
from app.dependencies import ProjectAccess, get_extraction_service, get_project_editor_access
from app.schemas.document import DocumentUploadResponse
from app.services.extraction_service import ExtractionService
from app.worker import extract_document_task

router = APIRouter(prefix="/api/projects/{project_id}", tags=["upload"])

@router.post("/documents", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
def upload_document(file: UploadFile = File(...), extraction_strategy: str = Form("AUTO"), document_type: str | None = Form(None), request_id: str = Depends(get_request_id), access: ProjectAccess = Depends(get_project_editor_access), service: ExtractionService = Depends(get_extraction_service)):
    if not file.filename:
        raise BusinessError(ErrorCode.INVALID_FILE_TYPE, detail="파일명이 필요합니다.")
    content = file.file.read(settings.max_file_size_bytes + 1)
    if len(content) > settings.max_file_size_bytes:
        raise BusinessError(ErrorCode.FILE_TOO_LARGE)
    if not content:
        raise BusinessError(ErrorCode.EXTRACTION_FAILED, detail="빈 파일은 업로드할 수 없습니다.")
    document = service.create_pending_upload(
        access.project.id,
        access.member.user_id,
        file.filename,
        content,
        extraction_strategy,
        document_type,
    )
    # request_id 를 태스크에 실어 보낸다 (SYS-003-1). 이것이 없으면 워커 로그를
    # 업로드 요청과 이어붙일 수 없다 — "업로드는 됐는데 텍스트가 안 나온다" 는
    # 신고에서 어느 요청이었는지 찾을 방법이 없어진다.
    try:
        extract_document_task.delay(access.project.id, document.id, request_id=request_id)
    except Exception as exc:
        service.discard_pending_upload(document)
        raise BusinessError(ErrorCode.PROCESS_QUEUE_UNAVAILABLE) from exc
    return DocumentUploadResponse(
        id=document.id, project_id=document.project_id, filename=document.filename,
        file_type=document.file_type, document_type=document.document_type,
        document_type_source=document.document_type_source,
        extraction_strategy=document.extraction_strategy,
        status=document.status, review_status=document.review_status, page_count=None,
        char_count=None, text_char_count=0, ocr_char_count=0,
        extract_method=None, processing_error=document.processing_error, created_at=document.created_at,
    )
