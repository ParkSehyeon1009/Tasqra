# =============================================================================
# 이 파일의 책임: documents 테이블에 대한 CRUD와 목록 검색/페이징 쿼리를 담당한다.
#   Service 레이어는 DB 세션(Session)을 직접 다루지 않고 반드시 이 Repository를
#   거쳐서만 documents에 접근한다 (§2-1 Router -> Service -> Repository 원칙).
# 다른 파일과의 관계: dependencies.py의 get_document_repository()가 Depends(get_db)로
#   받은 Session을 주입해 이 클래스를 생성한다. document_service.py(담당자 C)가
#   이 클래스를 호출한다. models/document.py의 Document/ExtractedText/Analysis를 사용.
# Spring 비교: Spring Data JPA의 DocumentRepository(JpaRepository<Document, Long>)와
#   같은 위치. 다만 Spring Data처럼 메서드 이름만으로 쿼리를 자동 생성해주지
#   않으므로, 검색·페이징 쿼리를 SQLAlchemy Query API로 직접 작성한다.
# =============================================================================

import re

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.document import Analysis, Document, DocumentPage, ExtractedText, OcrElement


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, document: Document) -> Document:
        self._db.add(document)
        self._db.flush()
        return document

    def get_by_id(self, project_id: int, document_id: int) -> Document | None:
        return self._db.query(Document).filter(Document.project_id == project_id, Document.id == document_id).one_or_none()

    def delete(self, document: Document) -> None:
        self._db.delete(document)

    def get_review_page(self, project_id: int, document_id: int, page_id: int) -> DocumentPage | None:
        return self._db.query(DocumentPage).join(Document).filter(Document.project_id == project_id, Document.id == document_id, DocumentPage.id == page_id).one_or_none()

    def get_ocr_element(self, project_id: int, document_id: int, element_id: int) -> OcrElement | None:
        return self._db.query(OcrElement).join(DocumentPage).join(Document).filter(Document.project_id == project_id, Document.id == document_id, OcrElement.id == element_id).one_or_none()

    def search(
        self,
        *,
        project_id: int,
        q: str | None,
        document_type: str | None,
        category: str | None,
        page: int,
        size: int,
    ) -> tuple[list[Document], int]:
        query = self._db.query(Document).filter(Document.project_id == project_id)

        if q:
            # 파일명 또는 본문(extracted_texts.content) 부분검색.
            # outerjoin 대신 서브쿼리로 매칭 id를 걸러서 join으로 인한 행 중복을 피한다.
            # 자간이 넓은 공문서는 추출 결과에 "제 안 자" 처럼 공백이 섞여 들어가므로,
            # 저장된 값과 검색어 양쪽에서 공백·줄바꿈을 제거한 뒤 비교한다.
            normalized_q = re.sub(r"\s+", "", q)

            # 공백만 입력된 경우에는 조건을 걸지 않는다 (전체 조회와 같아지는 것을 방지).
            if normalized_q:
                pattern = f"%{normalized_q}%"

                matching_ids = self._db.query(ExtractedText.document_id).filter(
                    func.regexp_replace(
                        ExtractedText.content, r"\s+", "", "g"
                    ).ilike(pattern)
                )
                query = query.filter(
                    or_(
                        func.regexp_replace(
                            Document.filename, r"\s+", "", "g"
                        ).ilike(pattern),
                        Document.id.in_(matching_ids),
                    )
                )


        if document_type:
            query = query.filter(Document.document_type == document_type)

        if category:
            # analyses.analyzer_type == "category"인 결과의 JSONB에서 category 값을 비교.
            matching_ids = self._db.query(Analysis.document_id).filter(
                Analysis.analyzer_type == "category",
                Analysis.result_json["category"].astext == category,
            )
            query = query.filter(Document.id.in_(matching_ids))

        total = query.count()
        items = (
            query.order_by(Document.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return items, total
