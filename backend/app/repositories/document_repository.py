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
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.document import Analysis, Document, DocumentPage, ExtractedText, OcrElement, OcrElementRevision
from app.models.enums import DocumentStatus, ReviewStatus
from app.models.user import User


UNCLASSIFIED_DOCUMENT_TYPE_FILTER = "__UNCLASSIFIED__"
DOCUMENT_STATE_FILTERS = {
    "PROCESSING": (
        Document.status.in_((
            DocumentStatus.PENDING.value,
            DocumentStatus.EXTRACTING.value,
            DocumentStatus.ANALYZING.value,
        )),
    ),
    "REVIEW_REQUIRED": (
        Document.review_status.in_((ReviewStatus.PENDING.value, ReviewStatus.IN_PROGRESS.value)),
    ),
    "COMPLETED": (
        Document.status.in_((DocumentStatus.EXTRACTED.value, DocumentStatus.COMPLETED.value)),
        Document.review_status.in_((ReviewStatus.NOT_REQUIRED.value, ReviewStatus.COMPLETED.value)),
    ),
    "FAILED": (Document.status == DocumentStatus.FAILED.value,),
}


class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, document: Document) -> Document:
        self._db.add(document)
        self._db.flush()
        return document

    def create_ocr_element(self, element: OcrElement) -> OcrElement:
        self._db.add(element)
        self._db.flush()
        return element

    def get_by_id(self, project_id: int, document_id: int) -> Document | None:
        return self._db.query(Document).filter(Document.project_id == project_id, Document.id == document_id).one_or_none()

    def get_by_id_with_review(self, project_id: int, document_id: int) -> Document | None:
        """OCR 검수 페이지와 요소를 컬렉션별 일괄 조회한다."""
        return (
            self._db.query(Document)
            .options(
                selectinload(Document.review_pages).selectinload(
                    DocumentPage.elements
                )
            )
            .filter(
                Document.project_id == project_id,
                Document.id == document_id,
            )
            .one_or_none()
        )

    def get_by_id_for_update(self, project_id: int, document_id: int) -> Document | None:
        return self._db.query(Document).filter(Document.project_id == project_id, Document.id == document_id).with_for_update().one_or_none()

    def get_by_id_for_update_with_review(
        self, project_id: int, document_id: int
    ) -> Document | None:
        """문서를 잠그면서 OCR 전체 순서를 계산할 관계를 일괄 조회한다."""
        return (
            self._db.query(Document)
            .options(
                joinedload(Document.extracted_text),
                selectinload(Document.review_pages).selectinload(
                    DocumentPage.elements
                ),
            )
            .filter(
                Document.project_id == project_id,
                Document.id == document_id,
            )
            .with_for_update(of=Document)
            .one_or_none()
        )

    def get_by_content_hash(self, project_id: int, content_hash: str) -> Document | None:
        return (
            self._db.query(Document)
            .filter(
                Document.project_id == project_id,
                Document.content_hash == content_hash,
            )
            .order_by(Document.created_at.desc())
            .first()
        )

    def delete(self, document: Document) -> None:
        self._db.delete(document)

    def get_review_page(self, project_id: int, document_id: int, page_id: int) -> DocumentPage | None:
        return self._db.query(DocumentPage).join(Document).filter(Document.project_id == project_id, Document.id == document_id, DocumentPage.id == page_id).one_or_none()

    def get_ocr_element(self, project_id: int, document_id: int, element_id: int) -> OcrElement | None:
        return self._db.query(OcrElement).join(DocumentPage).join(Document).filter(Document.project_id == project_id, Document.id == document_id, OcrElement.id == element_id).one_or_none()

    def get_ocr_element_for_update(self, project_id: int, document_id: int, element_id: int) -> OcrElement | None:
        return self._db.query(OcrElement).join(DocumentPage).join(Document).filter(Document.project_id == project_id, Document.id == document_id, OcrElement.id == element_id).with_for_update(of=OcrElement).one_or_none()

    def get_ocr_elements_for_update(self, project_id: int, document_id: int, element_ids: list[int]) -> list[OcrElement]:
        if not element_ids:
            return []
        return (
            self._db.query(OcrElement)
            .join(DocumentPage)
            .join(Document)
            .filter(
                Document.project_id == project_id,
                Document.id == document_id,
                OcrElement.id.in_(element_ids),
            )
            .with_for_update(of=OcrElement)
            .all()
        )

    def list_ocr_revisions(self, project_id: int, document_id: int) -> list[tuple[OcrElementRevision, str | None]]:
        return (
            self._db.query(OcrElementRevision, User.name)
            .join(OcrElement, OcrElement.id == OcrElementRevision.element_id)
            .join(DocumentPage, DocumentPage.id == OcrElement.page_id)
            .join(Document, Document.id == DocumentPage.document_id)
            .outerjoin(User, User.id == OcrElementRevision.changed_by)
            .filter(Document.project_id == project_id, Document.id == document_id)
            .order_by(OcrElementRevision.created_at.desc())
            .all()
        )

    def list_excluded_ocr_elements(self, document_id: int) -> list[OcrElement]:
        return self._db.query(OcrElement).join(DocumentPage).filter(DocumentPage.document_id == document_id, OcrElement.is_excluded.is_(True), OcrElement.is_deleted.is_(False)).order_by(DocumentPage.page_number, OcrElement.reading_order).all()

    def search(
        self,
        *,
        project_id: int,
        q: str | None,
        document_type: str | None,
        document_state: str | None,
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


        if document_type == UNCLASSIFIED_DOCUMENT_TYPE_FILTER:
            # URL에서만 쓰는 필터 값이다. 저장된 문서 유형이 아니며, 유형이 아직
            # 정해지지 않은 NULL 행을 대시보드 분포에서 그대로 열기 위해 번역한다.
            query = query.filter(Document.document_type.is_(None))
        elif document_type == "ETC":
            # BILLING·COST_SHEET는 과거 저장값이다. 7종 화면에서는 ETC에 편입한다.
            query = query.filter(Document.document_type.in_(("ETC", "BILLING", "COST_SHEET")))
        elif document_type:
            query = query.filter(Document.document_type == document_type)

        if document_state:
            query = query.filter(*DOCUMENT_STATE_FILTERS[document_state])

        if category:
            # analyses.analyzer_type == "category"인 결과의 JSONB에서 category 값을 비교.
            matching_ids = self._db.query(Analysis.document_id).filter(
                Analysis.analyzer_type == "category",
                Analysis.result_json["category"].astext == category,
            )
            query = query.filter(Document.id.in_(matching_ids))

        total = query.count()
        items = (
            query.options(joinedload(Document.extracted_text))
            .order_by(Document.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return items, total
