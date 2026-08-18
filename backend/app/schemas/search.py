# =============================================================================
# 이 파일의 책임: 의미 검색 API(RAG-04 = SRH-001)의 요청·응답 스키마를 정의한다.
#   필드명은 snake_case 그대로 둔다 — schemas/document.py 와 같은 규칙이고
#   프론트(React)도 snake_case 를 그대로 쓴다.
# 다른 파일과의 관계: api/routes/search_router.py 가 이 스키마로 주고받고,
#   services/search_service.py 가 ORM(DocumentChunk) -> 이 스키마로 옮긴다.
#   근거 스니펫(RAG-08 = SRH-002-2)이 P1 이라 결과마다 출처 문서와 원문 인용을
#   처음부터 함께 담는다. 나중에 붙이면 프론트 계약을 두 번 고쳐야 한다.
# Spring 비교: @RestController 가 주고받는 Request/Response DTO 다.
#   ConfigDict(from_attributes=True) 는 Entity -> DTO 정적 팩토리를
#   model_validate() 한 줄로 대신하는 것이다.
#
# 검색 범위를 목록으로 받는 이유
#   project_ids 를 단수(project_id)가 아니라 목록으로 둔 것은, 화면이 어떤 형태가
#   되어도 API 를 고치지 않으려는 것이다.
#     null        -> 내가 멤버인 모든 프로젝트
#     [3]         -> 현재 프로젝트만
#     [3, 7, 11]  -> 골라서 몇 개
#   토글(2가지)이든 프로젝트별 다중선택(N가지)이든 이 하나로 받는다.
#
#   기능명세서의 "다른 프로젝트 문서는 나오지 않는다"(RAG-04)는
#   "내가 멤버가 아닌 프로젝트는 나오지 않는다"로 읽는다. 그렇게 읽어야
#   RAG-12(SRH-002-3) "과거 유사 사업의 단가를 찾는다"와 모순되지 않는다.
#   과거 사업은 다른 프로젝트이므로, 앞 문장을 문자 그대로 읽으면 두 P1/P2
#   기능이 서로를 부정한다.
# =============================================================================

from pydantic import BaseModel, ConfigDict, Field

# 한 번에 돌려줄 결과 수의 상한. 청크는 문서 하나에 수백 개가 나오므로
# 상한이 없으면 응답이 커지고 HNSW 탐색 비용도 함께 커진다.
MAX_SEARCH_LIMIT = 50

# 한 번에 지정할 수 있는 프로젝트 수의 상한. 멤버십으로 걸러지므로 넘겨도
# 404 가 나지만, 터무니없이 긴 목록으로 검증 비용을 쓰게 하지 않으려는 것이다.
MAX_SCOPE_PROJECTS = 100


class SearchRequest(BaseModel):
    # 자연어 질의. "대금은 언제 주나요" 처럼 문서에 그 글자가 없어도 되는 것이
    # 의미 검색의 목적이다 (RAG-04 판정 기준).
    query: str = Field(min_length=1, max_length=1000)
    # 검색 범위. None 이면 내가 멤버인 모든 프로젝트.
    # 빈 목록([])은 받지 않는다 — "아무것도 검색하지 않겠다"는 뜻이 모호해서,
    # 전체를 원하면 명시적으로 null 을 쓰게 한다.
    project_ids: list[int] | None = Field(
        default=None, min_length=1, max_length=MAX_SCOPE_PROJECTS
    )
    limit: int = Field(default=10, ge=1, le=MAX_SEARCH_LIMIT)
    # 특정 문서 안에서만 찾고 싶을 때. 문서 상세 화면에서 쓸 수 있다.
    document_id: int | None = None
    # 이 값보다 유사도가 낮은 결과는 버린다. None 이면 상한 없이 limit 개까지.
    # 임계값을 몇으로 둘지는 실측 전에는 알 수 없어서 기본값을 두지 않는다.
    min_similarity: float | None = Field(default=None, ge=-1.0, le=1.0)


class SearchResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    document_id: int
    # 출처 표시용. 프론트가 문서 목록을 다시 조회하지 않게 함께 담는다 (RAG-08).
    document_filename: str
    # 전체 검색이면 결과가 여러 프로젝트에서 온다. 어느 프로젝트 문서인지
    # 모르면 결과를 읽을 수 없다. 조인으로 한 번에 가져온다 — chunk.document.
    # project.name 으로 접근하면 결과마다 두 단계 지연로딩(N+1)이 생긴다.
    project_id: int
    project_name: str
    seq: int
    page_number: int | None
    # 코사인 유사도. 1.0 이 가장 가깝다. pgvector 의 <=> 는 거리(0~2)를 주므로
    # 서비스에서 1 - distance 로 바꿔 담는다. 사람이 읽기 쉬운 쪽을 택했다.
    similarity: float
    # 원문 인용. 청크 전문이 아니라 앞부분을 잘라 담는다. 전문이 필요하면
    # 청크 상세를 따로 조회하게 둔다 — 목록 응답이 커지는 것을 막는다.
    #
    # 제목을 따로 담지 않는 이유: document_chunks 에 heading 컬럼이 없다.
    # chunking.py 가 Chunk.heading 을 계산하지만 저장하지 않고 버린다.
    # 다행히 청킹이 제목을 청크 본문 맨 앞에 오게 만들어 두므로(겹침 처리에서
    # 제목 뒤에 앞문맥을 넣는다), snippet 앞부분이 곧 제목이다.
    snippet: str
    # 청크 전체 길이. snippet 이 잘렸는지 프론트가 판단할 수 있게 한다.
    char_count: int
    # extracted_texts.content 안의 구간. 원문 대조에 쓴다. 모르면 null 이다.
    content_start: int | None
    content_end: int | None


class SearchResponse(BaseModel):
    query: str
    # 실제로 검색한 프로젝트 목록. 요청이 null 이었을 때 무엇으로 풀렸는지
    # 프론트가 알 수 있어야 한다 ("내 프로젝트 3곳에서 찾았습니다" 표시).
    searched_project_ids: list[int]
    # 어느 모델로 만든 벡터로 검색했는지. 모델을 바꾸면 결과가 달라지므로
    # 응답에 남겨야 나중에 "이 결과가 어느 모델 것인지"를 알 수 있다.
    # 값이 fake-hash-v1 이면 의미 없는 벡터라는 뜻이다 (개발용).
    embedding_model: str
    took_ms: int
    total: int
    results: list[SearchResultItem]
