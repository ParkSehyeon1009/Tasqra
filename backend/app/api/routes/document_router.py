from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import ProjectAccess, get_document_service, get_project_access, get_project_editor_access
from app.schemas.common import PageResponse
from app.schemas.document import AnalysisResponse, DocumentDetailResponse, DocumentListItem
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/projects/{project_id}", tags=["documents"])

@router.get("/documents", response_model=PageResponse[DocumentListItem])
def list_documents(q: str | None = None, document_type: str | None = None, category: str | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    rows, total, total_pages = service.search_documents(project_id=access.project.id, q=q, document_type=document_type, category=category, page=page, size=size)
    items = [DocumentListItem(id=row.document.id, filename=row.document.filename, document_type=row.document.document_type, status=row.document.status, category=row.category, summary_preview=row.summary_preview, created_at=row.document.created_at) for row in rows]
    return PageResponse(items=items, page=page, size=size, total=total, total_pages=total_pages)

@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: int, access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    document = service.get_document(access.project.id, document_id)
    extracted = document.extracted_text
    return DocumentDetailResponse(id=document.id, project_id=document.project_id, filename=document.filename, file_type=document.file_type, document_type=document.document_type, status=document.status, created_at=document.created_at, extracted_text=extracted.content if extracted else None, page_count=extracted.page_count if extracted else None, char_count=extracted.char_count if extracted else None, extract_method=extracted.extract_method if extracted else None, analyses=[AnalysisResponse.model_validate(item) for item in document.analyses])

@router.get("/documents/{document_id}/download")
def download_summary(document_id: int, format: str = Query("txt", pattern="^txt$"), access: ProjectAccess = Depends(get_project_access), service: DocumentService = Depends(get_document_service)):
    filename, content = service.build_summary_text(access.project.id, document_id)
    encoded = quote(filename)
    return Response(content=content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=\"summary.txt\"; filename*=UTF-8''{encoded}"})

@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, access: ProjectAccess = Depends(get_project_editor_access), service: DocumentService = Depends(get_document_service)):
    service.delete_document(access.project.id, document_id)
    return Response(status_code=204)
