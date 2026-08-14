# =============================================================================
# 이 파일의 책임: RAG 검색의 최소 단위인 "청크" 엔티티를 정의한다. 문서 본문을
#   잘라낸 텍스트 한 조각과 그 조각의 임베딩 벡터(1024차원)를 한 행으로 갖는다.
#   pgvector 의 HNSW 인덱스는 "테이블의 한 컬럼"을 색인하므로 벡터 하나가 반드시
#   행 하나여야 한다. 그래서 extracted_texts 에 배열로 넣지 않고 테이블을 분리했다.
# 다른 파일과의 관계: document.py 의 Document(1) : DocumentChunk(N) 이다.
#   content_start / content_end 는 extracted_texts.content 문자열 안의 위치이며,
#   같은 좌표계를 쓰는 ocr_elements(리비전 0010) 와 구간이 겹치는지로 교집합을
#   구해 원본 페이지 이미지의 x·y·width·height 를 얻는다 -> 검색 근거 하이라이트.
#   project_id 는 documents 에서 내려온 역정규화 컬럼이다(리비전 0014). 프로젝트
#   범위 벡터 검색에서 조건이 인덱스 스캔 단계로 내려가야 하기 때문이다.
#   models/__init__.py 에서 import 되어야 Base.metadata 에 등록된다.
# Spring 비교: JPA @Entity + @Table(uniqueConstraints=..., indexes=...) 에 대응한다.
#   Mapped[int] = mapped_column(...) 은 @Column 필드 선언과 같고,
#   relationship() 은 @OneToMany / @ManyToOne 에 해당한다. Vector 타입은 JPA 의
#   @Type(커스텀 UserType) 처럼 pgvector 가 제공하는 확장 컬럼 타입이다.
# =============================================================================

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# 채택 임베딩 모델의 출력 차원. dragonkue/BGE-m3-ko · KURE-v1 ·
# snowflake-arctic-embed-l-v2.0 이 모두 1024라서 모델을 바꿔도 DB 는 그대로다.
EMBEDDING_DIM = 1024


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        # 문서 안에서 청크 순서는 중복될 수 없다. (document_id, seq) 는 이 UNIQUE 가
        # 만드는 btree 인덱스로 조회도 함께 처리된다.
        UniqueConstraint("document_id", "seq", name="uq_document_chunk_seq"),
        CheckConstraint("seq >= 0", name="ck_document_chunk_seq"),
        CheckConstraint(
            "page_number IS NULL OR page_number >= 1",
            name="ck_document_chunk_page_number",
        ),
        CheckConstraint("char_count >= 0", name="ck_document_chunk_char_count"),
        CheckConstraint("token_count >= 0", name="ck_document_chunk_token_count"),
        CheckConstraint("text_version >= 1", name="ck_document_chunk_text_version"),
        CheckConstraint(
            f"embedding_dim = {EMBEDDING_DIM}", name="ck_document_chunk_embedding_dim"
        ),
        # 아래 둘은 ocr_elements 의 ck_ocr_element_content_{start,end} 와 같은 규칙이다.
        CheckConstraint(
            "content_start IS NULL OR content_start >= 0",
            name="ck_document_chunk_content_start",
        ),
        CheckConstraint(
            "content_end IS NULL OR content_end >= content_start",
            name="ck_document_chunk_content_end",
        ),
        # 낡은 청크 찾기: 청크의 text_version 이 extracted_texts.text_version 보다
        # 작으면 본문이 수정된 뒤 재청킹이 안 된 것이다.
        Index("ix_chunk_stale", "document_id", "text_version"),
        # 모델을 교체할 때 "이 모델로 만든 청크"만 골라 지우거나 다시 만든다.
        Index("ix_chunk_model", "embedding_model", "document_id"),
        # 벡터 유사도 검색용. 코사인 거리(vector_cosine_ops)로 색인한다.
        Index(
            "ix_chunk_vec",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # 프로젝트가 아주 작을 때는 HNSW 를 훑는 것보다 이 인덱스로 그 프로젝트의
        # 청크만 읽어 정확한 거리를 계산하는 편이 빠르다. 계획 선택지를 준다.
        Index("ix_chunk_project", "project_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # documents.project_id 의 역정규화. 프로젝트 범위 벡터 검색을 위한 것이며
    # 조회할 때 SET LOCAL hnsw.iterative_scan = strict_order 와 함께 쓴다.
    # 문서를 다른 프로젝트로 옮기는 기능이 생기면 이 값도 같이 갱신해야 한다.
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # extracted_texts.content 안에서 이 청크가 차지하는 구간 [content_start, content_end).
    # ocr_elements 와 같은 좌표계다. 청킹 규칙이 아직 확정되지 않았고 본문에서 위치를
    # 특정할 수 없는 경우(중복 문자열 등)가 있으므로 nullable 이다.
    content_start: Mapped[int | None] = mapped_column(Integer)
    content_end: Mapped[int | None] = mapped_column(Integer)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=EMBEDDING_DIM
    )
    text_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    document = relationship("Document", back_populates="chunks")

    @property
    def has_content_range(self) -> bool:
        """본문 좌표를 알고 있는 청크인지. False 면 하이라이트를 그릴 수 없고
        페이지 번호까지만 출처로 쓴다."""
        return self.content_start is not None and self.content_end is not None
