from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import FileResponse

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.middleware import current_request_id, get_request_id
from app.dependencies import ProjectAccess, get_document_service, get_extraction_service, get_project_access, get_project_editor_access
from app.schemas.common import PageResponse
from app.schemas.document import AnalysisResponse, DocumentDetailResponse, DocumentListItem, DocumentProcessingResponse, DocumentTypeUpdateRequest, DocumentTypeUpdateResponse, OcrElementBatchUpdateRequest, OcrElementBatchUpdateResponse, OcrElementCreateRequest, OcrElementDeletionRequest, OcrElementExclusionRequest, OcrElementMergeGroupsRequest, OcrElementMergeGroupsResponse, OcrElementMergeRequest, OcrElementMergeResponse, OcrElementMergeUndoResponse, OcrElementResponse, OcrElementUpdateRequest, OcrPageResponse, OcrReprocessRequest, OcrReprocessResponse, OcrReviewResponse, OcrRevisionResponse, OcrStructureEventResponse, OcrUndoableMergeResponse
from app.services.document_service import DocumentService, OcrElementBatchChange
from app.services.extraction_service import ExtractionService
from app.worker import enqueue_build_chunks, extract_document_task

router = APIRouter(prefix="/api/projects/{project_id}", tags=["documents"])

@router.get("/documents", response_model=PageResponse[DocumentListItem])
def list_documents(q: str | None = None, document_type: str | None = None, document_state: str | None = Query(None, pattern="^(PROCESSING|REVIEW_REQUIRED|COMPLETED|FAILED)$"), category: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    rows, total, total_pages = service.search_documents(project_id=access.project.id, q=q, document_type=document_type, document_state=document_state, category=category, page=page, size=size)
    items = [DocumentListItem(id=row.document.id, filename=row.document.filename, file_type=row.document.file_type, document_type=row.document.document_type, document_type_source=row.document.document_type_source, status=row.document.status, processing_error=row.document.processing_error, review_status=row.document.review_status, page_count=row.document.extracted_text.page_count if row.document.extracted_text else None, char_count=row.document.extracted_text.char_count if row.document.extracted_text else None, text_char_count=row.document.native_text_char_count, ocr_char_count=row.document.active_ocr_char_count, extract_method=row.document.extracted_text.extract_method if row.document.extracted_text else None, category=row.category, summary_preview=row.summary_preview, created_at=row.document.created_at) for row in rows]
    return PageResponse(items=items, page=page, size=size, total=total, total_pages=total_pages)

@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: int, access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    document = service.get_document(access.project.id, document_id)
    extracted = document.extracted_text
    return DocumentDetailResponse(id=document.id, project_id=document.project_id, filename=document.filename, file_type=document.file_type, document_type=document.document_type, document_type_source=document.document_type_source, status=document.status, processing_error=document.processing_error, review_status=document.review_status, extraction_strategy=document.extraction_strategy, uploaded_by_name=document.uploader.name if document.uploader else None, reviewed_by_name=document.reviewer.name if document.reviewer else None, reviewed_at=document.reviewed_at, created_at=document.created_at, extracted_text=extracted.content if extracted else None, page_count=extracted.page_count if extracted else None, char_count=extracted.char_count if extracted else None, extract_method=extracted.extract_method if extracted else None, text_version=extracted.text_version if extracted else None, is_confirmed=extracted.is_confirmed if extracted else False, analyses=[AnalysisResponse.model_validate(item) for item in document.analyses])

@router.patch("/documents/{document_id}/document-type", response_model=DocumentTypeUpdateResponse)
def update_document_type(document_id: int, payload: DocumentTypeUpdateRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    document = service.update_document_type(
        access.project.id,
        document_id,
        payload.document_type,
    )
    return DocumentTypeUpdateResponse.model_validate(document)

@router.post("/documents/{document_id}/retry", response_model=DocumentProcessingResponse)
def retry_document_processing(document_id: int, request_id: str = Depends(get_request_id), access: ProjectAccess = Depends(get_project_editor_access), service: ExtractionService = Depends(get_extraction_service)):
    document = service.prepare_retry(access.project.id, document_id)
    try:
        extract_document_task.delay(access.project.id, document.id, request_id=request_id)
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
    # 삭제한 영역도 검토 화면에는 내려줘야 새로고침 후 복원할 수 있다.
    # 원본 캔버스에서는 프런트가 삭제 영역을 숨기고 목록에서만 복원 동작을 제공한다.
    pages = [OcrPageResponse(id=page.id, page_number=page.page_number, page_kind=page.page_kind, width=page.width, height=page.height, image_url=f"/api/projects/{access.project.id}/documents/{document.id}/review/pages/{page.id}/image", elements=[OcrElementResponse.model_validate(item) for item in page.elements]) for page in document.review_pages]
    latest_merge = service.get_latest_undoable_merge(access.project.id, document_id)
    undoable_merges = service.list_undoable_merges(access.project.id, document_id)
    structure_history = service.list_ocr_structure_events(access.project.id, document_id)
    return OcrReviewResponse(document_id=document.id, review_status=document.review_status, ocr_revision=document.ocr_revision, ocr_char_count=sum(len(element.text) for page in pages for element in page.elements if not element.is_excluded and not element.is_deleted), latest_merge_operation_id=latest_merge[0] if latest_merge else None, latest_merge_page_id=latest_merge[1] if latest_merge else None, undoable_merges=[OcrUndoableMergeResponse(operation_id=item[0], survivor_id=item[1], page_id=item[2], original_count=item[3]) for item in undoable_merges], structure_history=[OcrStructureEventResponse(id=item.id, page_id=item.page_id, event_type=item.event_type, details=item.details_json, created_at=item.created_at) for item in structure_history], pages=pages)

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

@router.post("/documents/{document_id}/ocr-elements", response_model=OcrElementResponse, status_code=201)
def create_ocr_element(document_id: int, payload: OcrElementCreateRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    return OcrElementResponse.model_validate(service.create_ocr_element(access.project.id, document_id, payload.page_id, payload.text, payload.x, payload.y, payload.width, payload.height))

@router.patch("/documents/{document_id}/ocr-elements/{element_id}/deletion", response_model=OcrElementResponse)
def set_ocr_element_deletion(document_id: int, element_id: int, payload: OcrElementDeletionRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    return OcrElementResponse.model_validate(service.set_ocr_element_deletion(access.project.id, document_id, element_id, payload.is_deleted, payload.version))

@router.post("/documents/{document_id}/ocr-elements/{element_id}/reprocess", response_model=OcrReprocessResponse)
def reprocess_ocr_element(document_id: int, element_id: int, payload: OcrReprocessRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    element, recognized_text, confidence = service.reprocess_ocr_element(access.project.id, document_id, element_id, payload.x, payload.y, payload.width, payload.height)
    return OcrReprocessResponse(element_id=element.id, original_text=element.text, recognized_text=recognized_text, confidence=confidence)

@router.post("/documents/{document_id}/ocr-elements/merge", response_model=OcrElementMergeResponse)
def merge_ocr_elements(document_id: int, payload: OcrElementMergeRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    document, merged, deleted_ids, operation = service.merge_ocr_elements(access.project.id, document_id, [(item.id, item.version) for item in payload.items], access.member.user_id, payload.join_with_space)
    return OcrElementMergeResponse(ocr_revision=document.ocr_revision, text_version=document.extracted_text.text_version if document.extracted_text else None, merge_operation_id=operation.id, merged=OcrElementResponse.model_validate(merged), deleted_ids=deleted_ids)

@router.post("/documents/{document_id}/ocr-elements/merge-groups", response_model=OcrElementMergeGroupsResponse)
def merge_ocr_element_groups(document_id: int, payload: OcrElementMergeGroupsRequest, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    results = service.merge_ocr_element_groups(access.project.id, document_id, [[(item.id, item.version) for item in group] for group in payload.groups], access.member.user_id, payload.join_with_space)
    return OcrElementMergeGroupsResponse(items=[OcrElementMergeResponse(ocr_revision=document.ocr_revision, text_version=document.extracted_text.text_version if document.extracted_text else None, merge_operation_id=operation.id, merged=OcrElementResponse.model_validate(merged), deleted_ids=deleted_ids) for document, merged, deleted_ids, operation in results])

@router.post("/documents/{document_id}/ocr-elements/merge/{operation_id}/undo", response_model=OcrElementMergeUndoResponse)
def undo_ocr_merge(document_id: int, operation_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    document, restored, deleted_ids = service.undo_ocr_merge_to_originals(access.project.id, document_id, operation_id, access.member.user_id)
    return OcrElementMergeUndoResponse(ocr_revision=document.ocr_revision, text_version=document.extracted_text.text_version if document.extracted_text else None, deleted_ids=deleted_ids, restored=[OcrElementResponse.model_validate(item) for item in restored if not item.is_deleted])

@router.post("/documents/{document_id}/review/complete", response_model=OcrReviewResponse)
def complete_ocr_review(document_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    document = service.complete_ocr_review(access.project.id, document_id, access.member.user_id)
    # 검수가 확정되면 본문이 바뀌었을 수 있으므로 청킹·임베딩을 다시 돌린다 (RAG-001-3).
    # 여기서 부르는 이유: service 가 리턴한 시점에 transactional 이 이미 커밋했다.
    # 큐 등록이 실패해도 예외를 올리지 않아 검수 완료는 그대로 성공한다.
    # request_id 는 contextvar 에서 읽는다 (SYS-003-1). 이 엔드포인트 서명에
    # Depends 를 더하지 않는 이유는, 이 파일을 다른 사람이 만지고 있어서 서명을
    # 고치면 충돌 지점이 되기 때문이다. 값을 못 얻으면 "-" 이고 아무것도 깨지지 않는다.
    enqueue_build_chunks(access.project.id, document.id, reason="OCR 검수 확정 (RAG-001-3)", request_id=current_request_id())
    document = service.get_document_for_review(access.project.id, document.id)
    pages = [OcrPageResponse(id=page.id, page_number=page.page_number, page_kind=page.page_kind, width=page.width, height=page.height, image_url=f"/api/projects/{access.project.id}/documents/{document.id}/review/pages/{page.id}/image", elements=[OcrElementResponse.model_validate(item) for item in page.elements]) for page in document.review_pages]
    latest_merge = service.get_latest_undoable_merge(access.project.id, document_id)
    undoable_merges = service.list_undoable_merges(access.project.id, document_id)
    structure_history = service.list_ocr_structure_events(access.project.id, document_id)
    return OcrReviewResponse(document_id=document.id, review_status=document.review_status, ocr_revision=document.ocr_revision, ocr_char_count=sum(len(element.text) for page in pages for element in page.elements if not element.is_excluded and not element.is_deleted), latest_merge_operation_id=latest_merge[0] if latest_merge else None, latest_merge_page_id=latest_merge[1] if latest_merge else None, undoable_merges=[OcrUndoableMergeResponse(operation_id=item[0], survivor_id=item[1], page_id=item[2], original_count=item[3]) for item in undoable_merges], structure_history=[OcrStructureEventResponse(id=item.id, page_id=item.page_id, event_type=item.event_type, details=item.details_json, created_at=item.created_at) for item in structure_history], pages=pages)

@router.get("/documents/{document_id}/download")
def download_summary(document_id: int, format: str = Query("txt", pattern="^txt$"), access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    filename, content = service.build_summary_text(access.project.id, document_id)
    encoded = quote(filename)
    return Response(content=content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=\"summary.txt\"; filename*=UTF-8''{encoded}"})

@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    service.delete_document(access.project.id, document_id)
    return Response(status_code=204)
