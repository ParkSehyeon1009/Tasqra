# =============================================================================
# 이 파일의 책임: 문서 기반 질의응답 챗봇(CHAT-001)의 요청·모델 출력·HTTP 응답
#   DTO를 정의한다.
# 다른 파일과의 관계: chat_router.py가 요청·응답에, chat_service.py가 LLM의
#   구조화 JSON 검증과 실제 근거 매핑에 사용한다.
# Spring 비교: Controller DTO와 외부 AI 응답 DTO를 한 기능 패키지에 둔 형태다.
# =============================================================================

from pydantic import BaseModel, Field, field_validator


class ChatQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("질문은 비워둘 수 없습니다")
        return stripped


class ChatModelOutput(BaseModel):
    """LLM이 생성할 최소 결과. 출처 메타데이터는 서버가 붙인다."""

    answer: str = Field(min_length=1)
    # 검색 결과가 질문에 답하지 못하면 False로 두고 근거 번호를 비운다. 관련 없는
    # 청크에 억지로 출처를 붙이는 것보다 명시적으로 답변을 보류해야 한다.
    answerable: bool
    evidence_ids: list[int] = Field(default_factory=list)


class ChatEvidence(BaseModel):
    evidence_id: int
    chunk_id: int
    document_id: int
    document_filename: str
    project_id: int
    project_name: str
    seq: int
    page_number: int | None = None
    content_start: int | None = None
    content_end: int | None = None
    quote: str


class ChatResponse(BaseModel):
    answer: str
    evidence: list[ChatEvidence]
    searched_project_ids: list[int]
    model_name: str | None = None
    token_counter: str
    token_count_is_exact: bool
    context_limit_tokens: int
    answer_reserved_tokens: int
    message_framing_reserved_tokens: int
    evidence_budget_tokens: int
    evidence_used_tokens: int
