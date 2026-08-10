# =============================================================================
# 이 파일의 책임: 문서 목록·검색(GET /api/documents), 상세 조회
#   (GET /api/documents/{id}), 요약 다운로드(GET /api/documents/{id}/download)
#   엔드포인트를 정의한다. 요청 검증과 응답 스키마 변환만 하고 비즈니스 로직은
#   전부 DocumentService에 위임한다 (§2-1 Router -> Service -> Repository).
# 다른 파일과의 관계: dependencies.py의 get_document_service()를 Depends로 주입받고,
#   schemas/document.py(DocumentListItem/DocumentDetailResponse/AnalysisResponse),
#   schemas/common.py(PageResponse)로 응답을 만든다. main.py가 include_router()로 등록.
# Spring 비교: @RestController + @GetMapping 과 동일한 위치. Query 파라미터의
#   기본값·범위 검증(ge/le)은 Spring의 @RequestParam(defaultValue) + @Validated
#   @Min/@Max 에 대응한다. AI 호출이 없는 조회 전용이라 async 가 아닌 동기(def)
#   함수로 두어 FastAPI가 threadpool 에서 실행하게 한다 (동기 DB 세션 사용).
# =============================================================================

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import get_document_service
from app.schemas.common import PageResponse
from app.schemas.document import (
    AnalysisResponse,
    DocumentDetailResponse,
    DocumentListItem,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api", tags=["documents"])

@router.get("/documents", response_model=PageResponse[DocumentListItem])
def list_documents(
    q: str | None = Query(None, description="파일명 또는 본문 부분검색"),
    document_type: str | None = Query(None, description="문서 유형 필터"),
    category: str | None = Query(None, description="분석된 카테고리 필터"),
    page: int = Query(1, ge=1, description="1부터 시작"),
    size: int = Query(20, ge=1, le=100),
    service: DocumentService = Depends(get_document_service),
) -> PageResponse[DocumentListItem]:
    rows, total, total_pages = service.search_documents(
        q=q,
        document_type=document_type,
        category=category,
        page=page,
        size=size,
    )

    items = [
        DocumentListItem(
            id=row.document.id,
            filename=row.document.filename,
            document_type=row.document.document_type,
            status=row.document.status,
            category=row.category,
            summary_preview=row.summary_preview,
            created_at=row.document.created_at,
        )
        for row in rows
    ]

    return PageResponse[DocumentListItem](
        items=items,
        page=page,
        size=size,
        total=total,
        total_pages=total_pages,
    )

@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service),
) -> DocumentDetailResponse:
    document = service.get_document(document_id)
    extracted = document.extracted_text

    return DocumentDetailResponse(
        id=document.id,
        filename=document.filename,
        file_type=document.file_type,
        document_type=document.document_type,
        status=document.status,
        created_at=document.created_at,
        extracted_text=extracted.content if extracted else None,
        page_count=extracted.page_count if extracted else None,
        char_count=extracted.char_count if extracted else None,
        extract_method=extracted.extract_method if extracted else None,
        analyses=[
            AnalysisResponse.model_validate(analysis)
            for analysis in document.analyses
        ],
    )

@router.get("/documents/{document_id}/download")
def download_summary(
    document_id: int,
    format: str = Query("txt", alias="format", pattern="^txt$", description="현재 txt만 지원"),
    service: DocumentService = Depends(get_document_service),
) -> Response:
    filename, content = service.build_summary_text(document_id)

    # 한글 파일명이 깨지지 않도록 RFC 5987 형식(filename*=UTF-8'')으로 인코딩한다.
    # filename= 도 같이 남겨 구형 브라우저 호환을 확보한다.
    encoded = quote(filename)
    disposition = f"attachment; filename=\"summary.txt\"; filename*=UTF-8''{encoded}"

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )

@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    service: DocumentService = Depends(get_document_service),
) -> Response:
    """문서와 연관 데이터(추출 텍스트·분석 결과)를 삭제한다.

    본문이 없는 응답이므로 204 No Content 를 반환한다.
    """
    service.delete_document(document_id)
    return Response(status_code=204)
