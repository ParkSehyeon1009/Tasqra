# =============================================================================
# 이 파일의 책임: 문서 하나를 "청크 + 임베딩"으로 만들어 DB 에 넣는 전 과정을
#   조립한다 (RAG-001-1 청킹 · RAG-001-2 임베딩 생성·저장). 순서는 이렇다.
#     1. 문서와 확정 본문(extracted_texts)을 읽는다
#     2. 청킹 입력을 만든다 — ocr_elements 가 있으면 그것으로, 없으면 본문 평문으로
#     3. chunking.chunk_text 로 자른다 (순수 로직, 이 파일은 규칙을 모른다)
#     4. 임베딩 클라이언트로 벡터를 만든다 (구현체가 가짜인지 실제인지 모른다)
#     5. 기존 청크를 지우고 새로 넣는다 — 한 트랜잭션으로
#   여기서 project_id 를 채운다. documents.project_id 를 그대로 복사하는데,
#   이것을 빠뜨리면 리비전 0014(프로젝트 범위 벡터 검색)가 의미를 잃는다.
#   NOT NULL 이라 빠뜨리면 INSERT 가 실패하므로 조용히 넘어가지는 않는다.
#
# 다른 파일과의 관계:
#   - services/chunking.py — 자르는 규칙(순수 함수). 이 파일이 부른다.
#   - embedding/protocol.py — 벡터를 만드는 계약. 구현체는 dependencies 가 고른다.
#   - repositories/chunk_repository.py — document_chunks 접근.
#   - worker.py 의 chunks.build 태스크가 이 서비스를 부른다. 추출 파이프라인
#     (ExtractionService.process_document)에 끼워 넣지 않고 별도 태스크로 둔 이유:
#     문서 추출은 DOC 영역(담당 재정)이라 그쪽 코드를 건드리지 않으려는 것이다.
#     연결은 추출이 끝난 자리에 chunks.build.delay(...) 한 줄만 넣으면 된다.
#
# Spring 비교: @Service + @Transactional 클래스다. 생성자로 Session ·
#   Repository · EmbeddingClient 를 받는 것이 그대로 생성자 주입이고,
#   rebuild_for_document 하나가 트랜잭션 경계다.
# =============================================================================

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.embedding.protocol import EmbeddingClientProtocol
from app.core.constants import EMBEDDING_DIM
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentPage, ExtractedText, OcrElement
from app.repositories.chunk_repository import ChunkRepository
from app.services.chunking import (
    Chunk,
    CharRatioTokenCounter,
    TextUnit,
    TokenCounter,
    chunk_units,
    units_from_elements,
    units_from_plain_text,
)

logger = logging.getLogger(__name__)


class ChunkingService:
    def __init__(
        self,
        db: Session,
        chunk_repository: ChunkRepository,
        embedding_client: EmbeddingClientProtocol,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._db = db
        self._chunks = chunk_repository
        self._embedder = embedding_client
        # 기본은 문자 수 기반 근사다. 실제 토크나이저를 쓰려면 여기에
        # 다른 구현을 넣으면 되고 chunking.py 는 고치지 않는다.
        self._counter = token_counter or CharRatioTokenCounter()

    # --- 공개 API -----------------------------------------------------------

    def rebuild_for_document(self, project_id: int, document_id: int) -> int:
        """문서 하나의 청크를 전부 다시 만든다. 만든 청크 수를 돌려준다.

        "다시 만든다"인 이유: 본문이 수정되면(OCR 검수) 기존 청크는 낡은 것이
        되고, 부분 갱신은 어느 청크가 어느 문장에 대응하는지 추적해야 해서
        훨씬 복잡하다. 문서 하나의 청크는 수백 개 규모라 전부 다시 만들어도
        비용이 크지 않다. RAG-001-3(검수 확정 시 재임베딩)도 이 메서드를 부른다.
        """
        document = self._load_document(project_id, document_id)
        if document is None:
            logger.warning(
                "청킹 대상 문서를 찾지 못했다 project_id=%s document_id=%s",
                project_id,
                document_id,
            )
            return 0

        extracted = document.extracted_text
        if extracted is None or not extracted.content.strip():
            logger.info(
                "본문이 없어 청킹을 건너뛴다 document_id=%s (추출 전이거나 빈 문서)",
                document_id,
            )
            # 기존 청크는 지운다. RAG-001-3 로 검수 확정에서도 이 경로가 닿게 되면서
            # 필요해졌다 — 검수에서 요소를 전부 제외하면 본문이 비는데, 청크를
            # 남겨두면 지워진 내용이 검색에 계속 나온다. 아래 "청크가 만들어지지
            # 않았다" 분기도 같은 이유로 지우고 있어서 두 경로를 맞췄다.
            if self._chunks.delete_for_document(document_id):
                self._db.commit()
            return 0

        # 이미 이 본문 판과 이 모델로 만든 청크가 있으면 건너뛴다 (RAG-001-3).
        # 검수 확정은 본문이 하나도 바뀌지 않아도 일어나므로, 그때마다 수백
        # 청크를 다시 임베딩하면 낭비다 (건당 244~519ms).
        #
        # 모델 이름을 임베딩 결과가 아니라 클라이언트에게 미리 묻는 것이 핵심이다.
        # result.model 은 임베딩을 실제로 돌린 뒤에야 알 수 있어서, 돌릴지 말지
        # 판단하는 데는 쓸 수 없다. Protocol 에 model_name 이 있는 이유가 이것이다.
        if self._chunks.is_current_for_document(
            document_id,
            text_version=extracted.text_version,
            model=self._embedder.model_name,
        ):
            count = self._chunks.count_for_document(document_id)
            logger.info(
                "청크가 이미 최신이라 재청킹을 건너뛴다 document_id=%s text_version=%d 청크=%d",
                document_id,
                extracted.text_version,
                count,
            )
            return count

        units = self._build_units(document, extracted)
        chunks = chunk_units(
            units,
            counter=self._counter,
            max_tokens=settings.CHUNK_MAX_TOKENS,
            min_tokens=settings.CHUNK_MIN_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
        )
        if not chunks:
            logger.info("청크가 만들어지지 않았다 document_id=%s", document_id)
            # 기존 청크는 낡은 것이므로 지운다. 본문이 비워진 경우다.
            self._chunks.delete_for_document(document_id)
            self._db.commit()
            return 0

        result = self._embedder.embed_documents([c.text for c in chunks])
        self._validate_embeddings(chunks, result)

        rows = [
            self._to_row(
                chunk=chunk,
                vector=vector,
                document=document,
                text_version=extracted.text_version,
                model=result.model,
                dimension=result.dimension,
            )
            for chunk, vector in zip(chunks, result.vectors)
        ]

        # 지우고 넣는 것을 한 트랜잭션에서 한다. 중간에 실패하면 옛 청크가
        # 그대로 남는다 — 낡은 벡터가 남는 것이 아무것도 없는 것보다 낫다.
        self._chunks.delete_for_document(document_id)
        self._chunks.bulk_insert(rows)
        self._db.commit()

        logger.info(
            "청킹 완료 document_id=%s project_id=%s 청크=%d 모델=%s text_version=%d",
            document_id,
            document.project_id,
            len(rows),
            result.model,
            extracted.text_version,
        )
        return len(rows)

    # --- 내부 ---------------------------------------------------------------

    def _load_document(self, project_id: int, document_id: int) -> Document | None:
        stmt = (
            select(Document)
            .where(Document.id == document_id)
            .where(Document.project_id == project_id)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def _build_units(
        self, document: Document, extracted: ExtractedText
    ) -> list[TextUnit]:
        """청킹 입력을 만든다. 구조 정보가 있으면 쓰고, 없으면 평문으로 돌아간다.

        ocr_elements 를 쓰는 쪽이 낫다 — 페이지 번호와 표 정보(table_id ·
        table_row)를 알 수 있다. 다만 두 경우에 없다.
          (1) 검수 페이지가 만들어지지 않은 문서 (PDF 텍스트 레이어만 있는 경우)
          (2) 아직 추출 파이프라인이 구조를 채우지 않은 문서
        그래서 없으면 extracted_texts.content 를 줄 단위로 쪼갠다. 두 경로 모두
        content_start / content_end 를 같은 좌표계로 채운다.
        """
        elements = self._load_elements(document.id)
        if elements:
            return units_from_elements(elements)

        logger.info(
            "ocr_elements 가 없어 본문 평문으로 청킹한다 document_id=%s", document.id
        )
        return units_from_plain_text(extracted.content)

    def _load_elements(self, document_id: int) -> list[TextUnit]:
        """검수 요소를 읽어 TextUnit 으로 바꾼다.

        읽는 순서가 곧 청크 순서이므로 (page_number, page_id, reading_order) 로
        정렬한다. page_id 를 동점 처리로 넣은 이유:

        document_pages 에는 page_kind 가 두 종류다 — "PAGE" 와, 문서 안에 박힌
        이미지를 OCR 한 "EMBEDDED_IMAGE"(extractors/review_page.py). 지금은
        docx · hwpx 모두 len(review_pages) + 1 로 문서 단위 연번을 매겨서 같은
        page_number 가 둘 생기지 않는다. 하지만 그 규칙이 바뀌어 번호가 겹치면
        reading_order 는 페이지마다 다시 시작하므로 두 페이지의 요소가 서로
        섞인다. 에러가 나지 않고 청크 내용만 조용히 달라지는 종류의 고장이다.
        page_id 를 끼워 두면 삽입 순서(=추출 순서)로 항상 결정적이 된다.

        지운 것 · 제외한 것 · 본문에 안 들어간 것은 뺀다 — 본문(content)에
        반영되지 않은 요소를 청킹하면 content_start 좌표가 본문과 어긋난다.
        """
        stmt = (
            select(OcrElement, DocumentPage.page_number)
            .join(DocumentPage, DocumentPage.id == OcrElement.page_id)
            .where(DocumentPage.document_id == document_id)
            .where(OcrElement.is_deleted.is_(False))
            .where(OcrElement.is_excluded.is_(False))
            .where(OcrElement.is_in_content.is_(True))
            .order_by(
                DocumentPage.page_number,
                DocumentPage.id,
                OcrElement.reading_order,
            )
        )
        rows = self._db.execute(stmt).all()
        return [
            TextUnit(
                text=element.text,
                page_number=page_number,
                element_type=element.element_type,
                is_paragraph_start=element.is_paragraph_start,
                table_id=element.table_id,
                table_row=element.table_row,
                content_start=element.content_start,
                content_end=element.content_end,
            )
            for element, page_number in rows
        ]

    def _validate_embeddings(self, chunks: list[Chunk], result) -> None:
        """벡터 수와 차원을 확인한다.

        둘 중 하나라도 어긋나면 조용히 잘못 저장되는 것이 최악이다. 개수가
        어긋나면 zip 이 짧은 쪽에서 멈춰 뒤쪽 청크가 사라지고, 차원이 어긋나면
        document_chunks 의 embedding_dim CHECK 제약에서 걸린다. 그 전에 잡는다.
        """
        if len(result.vectors) != len(chunks):
            raise ValueError(
                f"임베딩 개수가 청크 수와 다르다: 청크 {len(chunks)}, "
                f"벡터 {len(result.vectors)} (모델 {result.model})"
            )
        if result.dimension != EMBEDDING_DIM:
            raise ValueError(
                f"임베딩 차원이 스키마와 다르다: 기대 {EMBEDDING_DIM}, "
                f"실제 {result.dimension} (모델 {result.model}). "
                "document_chunks 에 embedding_dim CHECK 제약이 있어 저장할 수 없다."
            )

    @staticmethod
    def _to_row(
        *,
        chunk: Chunk,
        vector: tuple[float, ...],
        document: Document,
        text_version: int,
        model: str,
        dimension: int,
    ) -> DocumentChunk:
        return DocumentChunk(
            document_id=document.id,
            # 여기가 리비전 0014 의 핵심이다. documents.project_id 를 그대로
            # 복사해 둬야 벡터 검색에서 WHERE project_id = X 가 "같은 테이블
            # 조건"이 되고, HNSW 의 iterative_scan 이 그 조건을 인덱스 스캔
            # 단계에서 평가할 수 있다. 조인으로 걸면 해당되지 않는다.
            project_id=document.project_id,
            seq=chunk.seq,
            page_number=chunk.page_number,
            text=chunk.text,
            char_count=chunk.char_count,
            token_count=chunk.token_count,
            content_start=chunk.content_start,
            content_end=chunk.content_end,
            embedding=list(vector),
            embedding_model=model,
            embedding_dim=dimension,
            text_version=text_version,
        )
