# =============================================================================
# 이 파일의 책임: document_chunks 테이블에 대한 조회 · 삽입 · 삭제를 담당한다.
#   비즈니스 판단은 하지 않는다 (그건 services/chunking_service.py 가 한다).
# 다른 파일과의 관계: models/chunk.py 의 DocumentChunk 를 다룬다.
#   services/chunking_service.py 가 이것을 주입받아 쓴다.
#   dependencies.py 의 get_chunk_repository() 가 세션을 감싸 만든다.
# Spring 비교: JpaRepository 를 상속한 인터페이스 + 커스텀 쿼리 메서드에 대응한다.
#   Session 을 생성자로 받는 것은 EntityManager 주입과 같다. commit 은 여기서
#   하지 않는다 — 서비스가 트랜잭션 경계를 잡는다(@Transactional 이 서비스에
#   붙는 것과 같은 이유).
# =============================================================================

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk


class ChunkRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # --- 조회 ---------------------------------------------------------------

    def count_for_document(self, document_id: int) -> int:
        stmt = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
        return int(self._db.execute(stmt).scalar_one())

    def list_for_document(self, document_id: int) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.seq)
        )
        return list(self._db.execute(stmt).scalars())

    def stale_document_ids(self, project_id: int) -> list[int]:
        """본문이 수정됐는데 재청킹이 안 된 문서를 찾는다.

        청크의 text_version 이 extracted_texts.text_version 보다 작으면 낡은
        것이다 (models/chunk.py 의 ix_chunk_stale 인덱스가 이 조회용이다).
        RAG-09(검수 확정 시 재임베딩)가 놓친 문서를 찾는 데 쓴다.
        """
        # ExtractedText 를 여기서 import 하면 순환이 생기지 않는다 (모델끼리는
        # 이미 서로를 알고 있다).
        from app.models.document import Document, ExtractedText

        stmt = (
            select(DocumentChunk.document_id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(ExtractedText, ExtractedText.document_id == Document.id)
            .where(DocumentChunk.project_id == project_id)
            .where(DocumentChunk.text_version < ExtractedText.text_version)
            .group_by(DocumentChunk.document_id)
        )
        return [int(row) for row in self._db.execute(stmt).scalars()]

    # --- 쓰기 ---------------------------------------------------------------

    def delete_for_document(self, document_id: int, *, model: str | None = None) -> int:
        """문서의 청크를 지운다.

        model 을 주면 그 모델로 만든 것만 지운다. 임베딩 모델을 교체할 때
        "옛 모델 청크만 버리고 새로 만든다"를 하려는 것이고, models/chunk.py 의
        ix_chunk_model (embedding_model, document_id) 인덱스가 이 조회용이다.
        """
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        if model is not None:
            stmt = stmt.where(DocumentChunk.embedding_model == model)
        result = self._db.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, chunks: list[DocumentChunk]) -> int:
        """청크를 한 번에 넣는다.

        add_all 은 flush 시점에 executemany 로 묶여 나가므로 한 건씩 add 하는
        것보다 왕복이 적다. commit 은 서비스가 한다.
        """
        if not chunks:
            return 0
        self._db.add_all(chunks)
        self._db.flush()
        return len(chunks)
