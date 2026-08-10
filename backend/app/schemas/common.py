# =============================================================================
# 이 파일의 책임: 목록 조회 API에서 공통으로 쓰는 페이징 응답 스키마를 정의한다.
# 다른 파일과의 관계: GET /api/documents(문서 목록·검색) 라우터(document_router.py,
#   담당자 C가 구현)가 PageResponse[DocumentListItem] 형태로 응답을 감싼다.
# Spring 비교: Spring Data의 Page<T>(content, number, size, totalElements,
#   totalPages)와 동일한 목적의 DTO. 필드명만 이 프로젝트 컨벤션(snake_case)에
#   맞춰 items/page/size/total/total_pages로 둔다.
# =============================================================================

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int
    total_pages: int
