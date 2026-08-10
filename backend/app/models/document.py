# =============================================================================
# 이 파일의 책임: PDF Brief AI의 핵심 엔티티 3종(Document, ExtractedText,
#   Analysis)을 SQLAlchemy 모델로 정의한다. documents:extracted_texts는 1:1,
#   documents:analyses는 1:N 관계이며, 재분석/모델 비교 실험을 위해 절대
#   테이블을 하나로 합치지 않는다 (documents에 summary 컬럼을 두는 식의 단순화 금지).
# 다른 파일과의 관계: db/base.py의 Base를 상속한다. repositories/*가 이 모델로
#   쿼리하고, schemas/document.py가 이 모델을 API 응답 스키마로 변환한다.
#   document_type은 문자열 컬럼일 뿐 AI 모델 선택 값이 아니다 — 단순 분류 라벨.
# Spring 비교: JPA @Entity + @OneToOne/@OneToMany와 동일한 매핑.
#   Document.extracted_text = @OneToOne(mappedBy="document"),
#   Document.analyses = @OneToMany(mappedBy="document")에 대응한다.
# =============================================================================

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    stored_path = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)
    file_size = Column(Integer, nullable=False)
    document_type = Column(String(50), nullable=False, default="general")
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    extracted_text = relationship(
        "ExtractedText",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    analyses = relationship(
        "Analysis",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class ExtractedText(Base):
    __tablename__ = "extracted_texts"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, unique=True)
    content = Column(Text, nullable=False)
    page_count = Column(Integer, nullable=False)
    char_count = Column(Integer, nullable=False)
    extract_method = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    document = relationship("Document", back_populates="extracted_text")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    analyzer_type = Column(String(30), nullable=False)
    result_json = Column(JSONB, nullable=False)
    provider = Column(String(30), nullable=False)
    model_name = Column(String(50), nullable=False)
    prompt_version = Column(String(20), nullable=False)
    # 본프로젝트에서 자체 파인튜닝 모델 vs 상용 API 비교 실험에 쓰이므로
    # 이 세 컬럼(tokens_in/tokens_out/latency_ms)은 생략하지 않는다.
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    document = relationship("Document", back_populates="analyses")

    # AnalysisResponse 스키마의 필드명은 result 인데 컬럼명은 result_json 이므로,
    # ORM -> 스키마 변환(model_validate)에서 찾을 수 있도록 별칭을 제공한다.
    @property
    def result(self) -> dict:
        return self.result_json

