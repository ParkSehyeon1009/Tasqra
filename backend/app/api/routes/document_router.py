from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.dependencies import ProjectAccess, get_document_service, get_extraction_service, get_project_access, get_project_editor_access
from app.schemas.common import PageResponse
from app.schemas.document import AnalysisResponse, DocumentDetailResponse, DocumentListItem, DocumentProcessingResponse, OcrElementBatchUpdateRequest, OcrElementBatchUpdateResponse, OcrElementExclusionRequest, OcrElementResponse, OcrElementUpdateRequest, OcrPageResponse, OcrReviewResponse, OcrRevisionResponse
from app.services.document_service import DocumentService, OcrElementBatchChange
from app.services.extraction_service import ExtractionService
from app.worker import enqueue_build_chunks, extract_document_task

router = APIRouter(prefix="/api/projects/{project_id}", tags=["documents"])

@router.get("/documents", response_model=PageResponse[DocumentListItem])
def list_documents(q: str | None = None, document_type: str | None = None, category: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    rows, total, total_pages = service.search_documents(project_id=access.project.id, q=q, document_type=document_type, category=category, page=page, size=size)
    items = [DocumentListItem(id=row.document.id, filename=row.document.filename, file_type=row.document.file_type, document_type=row.document.document_type, status=row.document.status, processing_error=row.document.processing_error, review_status=row.document.review_status, page_count=row.document.extracted_text.page_count if row.document.extracted_text else None, char_count=row.document.extracted_text.char_count if row.document.extracted_text else None, text_char_count=row.document.native_text_char_count, ocr_char_count=row.document.active_ocr_char_count, extract_method=row.document.extracted_text.extract_method if row.document.extracted_text else None, category=row.category, summary_preview=row.summary_preview, created_at=row.document.created_at) for row in rows]
    return PageResponse(items=items, page=page, size=size, total=total, total_pages=total_pages)

@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: int, access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    document = service.get_document(access.project.id, document_id)
    extracted = document.extracted_text
    return DocumentDetailResponse(id=document.id, project_id=document.project_id, filename=document.filename, file_type=document.file_type, document_type=document.document_type, status=document.status, processing_error=document.processing_error, review_status=document.review_status, extraction_strategy=document.extraction_strategy, uploaded_by_name=document.uploader.name if document.uploader else None, reviewed_by_name=document.reviewer.name if document.reviewer else None, reviewed_at=document.reviewed_at, created_at=document.created_at, extracted_text=extracted.content if extracted else None, page_count=extracted.page_count if extracted else None, char_count=extracted.char_count if extracted else None, extract_method=extracted.extract_method if extracted else None, text_version=extracted.text_version if extracted else None, is_confirmed=extracted.is_confirmed if extracted else False, analyses=[AnalysisResponse.model_validate(item) for item in document.analyses])

@router.post("/documents/{document_id}/retry", response_model=DocumentProcessingResponse)
def retry_document_processing(document_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: ExtractionService = Depends(get_extraction_service)):
    document = service.prepare_retry(access.project.id, document_id)
    try:
        extract_document_task.delay(access.project.id, document.id)
    except Exception as exc:
        service.mark_queue_failure(access.project.id, document.id)
        raise BusinessError(ErrorCode.PROCESS_QUEUE_UNAVAILABLE) from exc
    return DocumentProcessingResponse(document_id=document.id, status=document.status)

@router.get("/documents/{document_id}/source")
def download_source(document_id: int, access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    document = service.get_document(access.project.id, document_id)
    return FileResponse(document.storage_path, filename=document.filename, media_type="application/octet-stream")

@router.get("/documents/{document_id}/history", response_model=list[OcrRevisionResponse])
def get_document_history(document_id: int, access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    return [OcrRevisionResponse(id=item.id, element_id=item.element_id, changed_by_name=name, before_text=item.before_text, after_text=item.after_text, from_version=item.from_version, to_version=item.to_version, created_at=item.created_at) for item, name in service.list_ocr_revisions(access.project.id, document_id)]

@router.get("/documents/{document_id}/review", response_model=OcrReviewResponse)
def get_ocr_review(document_id: int, access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    document = service.get_document_for_review(access.project.id, document_id)
    pages = [OcrPageResponse(id=page.id, page_number=page.page_number, page_kind=page.page_kind, width=page.width, height=page.height, image_url=f"/api/projects/{access.project.id}/documents/{document.id}/review/pages/{page.id}/image", elements=[OcrElementResponse.model_validate(item) for item in page.elements if not item.is_deleted]) for page in document.review_pages]
    return OcrReviewResponse(document_id=document.id, review_status=document.review_status, ocr_revision=document.ocr_revision, ocr_char_count=sum(len(element.text) for page in pages for element in page.elements if not element.is_excluded), pages=pages)

@router.get("/documents/{document_id}/review/pages/{page_id}/image")
def get_ocr_page_image(document_id: int, page_id: int, access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    page = service.get_review_page(access.project.id, document_id, page_id)
    return FileResponse(page.image_path, media_type="image/png")

@router.patch("/documents/{document_id}/ocr-elements/{element_id}", response_model=OcrElementResponse)
def update_ocr_element(document_id: int, element_id: int, payload: OcrElementUpdateRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    return OcrElementResponse.model_validate(service.update_ocr_element(access.project.id, document_id, element_id, payload.text, payload.version, access.member.user_id))

@router.patch("/documents/{document_id}/ocr-elements", response_model=OcrElementBatchUpdateResponse)
def update_ocr_elements_batch(document_id: int, payload: OcrElementBatchUpdateRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    document, elements = service.update_ocr_elements_batch(
        access.project.id,
        document_id,
        [OcrElementBatchChange(**item.model_dump()) for item in payload.items],
        access.member.user_id,
    )
    return OcrElementBatchUpdateResponse(
        ocr_revision=document.ocr_revision,
        text_version=document.extracted_text.text_version if document.extracted_text else None,
        items=[OcrElementResponse.model_validate(element) for element in elements],
    )

@router.patch("/documents/{document_id}/ocr-elements/{element_id}/exclusion", response_model=OcrElementResponse)
def set_ocr_element_exclusion(document_id: int, element_id: int, payload: OcrElementExclusionRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    return OcrElementResponse.model_validate(service.set_ocr_element_exclusion(access.project.id, document_id, element_id, payload.is_excluded, payload.version))

@router.post("/documents/{document_id}/review/complete", response_model=OcrReviewResponse)
def complete_ocr_review(document_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    document = service.complete_ocr_review(access.project.id, document_id, access.member.user_id)
    # 검수가 확정되면 본문이 바뀌었을 수 있으므로 청킹·임베딩을 다시 돌린다 (RAG-09).
    # 여기서 부르는 이유: service 가 리턴한 시점에 transactional 이 이미 커밋했다.
    # 큐 등록이 실패해도 예외를 올리지 않아 검수 완료는 그대로 성공한다.
    enqueue_build_chunks(access.project.id, document.id, reason="OCR 검수 확정 (RAG-09)")
    document = service.get_document_for_review(access.project.id, document.id)
    pages = [OcrPageResponse(id=page.id, page_number=page.page_number, page_kind=page.page_kind, width=page.width, height=page.height, image_url=f"/api/projects/{access.project.id}/documents/{document.id}/review/pages/{page.id}/image", elements=[OcrElementResponse.model_validate(item) for item in page.elements if not item.is_deleted]) for page in document.review_pages]
    return OcrReviewResponse(document_id=document.id, review_status=document.review_status, ocr_revision=document.ocr_revision, ocr_char_count=sum(len(element.text) for page in pages for element in page.elements if not element.is_excluded), pages=pages)

@router.get("/documents/{document_id}/download")
def download_summary(document_id: int, format: str = Query("txt", pattern="^txt$"), access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    filename, content = service.build_summary_text(access.project.id, document_id)
    encoded = quote(filename)
    return Response(content=content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=\"summary.txt\"; filename*=UTF-8''{encoded}"})

@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    service.delete_document(access.project.id, document_id)
    return Response(status_code=204)
