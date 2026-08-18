# =============================================================================
# 이 파일의 책임: 의미 검색(RAG-04 = SRH-001)을 조립한다. 순서는 이렇다.
#     1. 검색 범위를 정한다 — 요청이 준 프로젝트 목록, 또는 내 멤버십 전체
#     2. 범위의 모든 프로젝트가 내 멤버십에 있는지 확인한다 (권한)
#     3. 질의를 벡터로 만든다
#     4. 그 범위 안에서 가까운 청크를 찾는다
#     5. 결과마다 출처와 원문 인용을 붙인다 (RAG-08 = SRH-002-2)
#   자르는 규칙도 임베딩 방법도 모른다 — 그 둘은 주입받은 것에 맡긴다.
#
# 다른 파일과의 관계:
#   - embedding/protocol.py — 질의를 벡터로 만드는 계약. 구현체가 가짜인지
#     실제인지 이 파일은 모른다.
#   - repositories/chunk_repository.py — 벡터 검색. project_id 와
#     embedding_model 조건이 거기 들어 있다.
#   - repositories/project_repository.py — 멤버십 확인.
#   - schemas/search.py — 응답 모양.
#   - api/routes/search_router.py 가 이 서비스를 부른다.
#
# 권한을 라우터가 아니라 서비스에서 확인하는 이유
#   기존 라우터들은 Depends(get_project_access) 로 경로의 project_id 를 검사한다.
#   검색은 경로에 프로젝트가 없고(POST /api/search) 범위가 여러 개일 수 있어서
#   그 의존성을 쓸 수 없다. 그래서 여기서 멤버십을 확인한다. 보장 수준은 같다 —
#   멤버가 아닌 프로젝트를 지정하면 PROJECT_NOT_FOUND 로 막는다(존재 자체를 숨긴다).
#
# 쿼리를 두 번 내는 것은 N+1 이 아니다
#   ① 멤버십 목록 1회 ② 벡터 검색 1회 = 항상 2회다. 프로젝트가 3개든 100개든
#   2회다. N+1 은 "목록 1회 + 항목마다 1회 = 1+N" 인 경우를 말한다.
#   오히려 Spring 에서 N+1 을 고치는 표준 방법(id 목록을 모아 IN 으로 한 번에
#   조회, @BatchSize 가 하는 일)과 같은 방향이다.
#   조인 하나로 1회로 줄일 수도 있지만, 그러면 project_id 조건이 조인 조건이 되어
#   리비전 0014 의 전제가 깨진다. 밀리초짜리 쿼리 하나를 더 내고 벡터 검색의
#   정확성을 지키는 거래다.
#
# Spring 비교: @Service 클래스다. 읽기만 하므로 @Transactional(readOnly = true)
#   에 해당한다. 다만 SET LOCAL 을 쓰기 때문에 트랜잭션 안이어야 한다.
# =============================================================================

from __future__ import annotations

import logging
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.embedding.protocol import EmbeddingClientProtocol
from app.repositories.chunk_repository import ChunkRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.search import SearchRequest, SearchResponse, SearchResultItem

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(
        self,
        db: Session,
        chunk_repository: ChunkRepository,
        project_repository: ProjectRepository,
        embedding_client: EmbeddingClientProtocol,
    ) -> None:
        self._db = db
        self._chunks = chunk_repository
        self._projects = project_repository
        self._embedder = embedding_client

    # --- 공개 API -----------------------------------------------------------

    def search(self, user_id: int, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()
        scope = self._resolve_scope(user_id, request.project_ids)

        if not scope:
            # 멤버인 프로젝트가 없다. 오류가 아니라 결과가 없는 것이다.
            return self._empty(request, scope, started)

        # 질의 임베딩은 문서 임베딩과 따로 부른다. BGE-M3 계열은 양쪽이 같지만
        # E5 계열은 질의에 "query: " 접두어를 붙여야 한다. 그 차이를 서비스가
        # 알지 않도록 embed_query 로 분리해 뒀다.
        embedded = self._embedder.embed_query(request.query.strip())
        if not embedded.vectors:
            logger.warning("질의 임베딩이 비어 있다 user_id=%s", user_id)
            return self._empty(request, scope, started, model=embedded.model)

        rows = self._chunks.search_by_vector(
            project_ids=scope,
            vector=list(embedded.vectors[0]),
            # 지금 쓰는 모델로 만든 청크만 본다. 이 조건이 없으면 옛 모델이나
            # 가짜 임베더로 만든 청크가 섞여, 서로 다른 벡터 공간의 거리를
            # 에러 없이 계산해 버린다.
            embedding_model=embedded.model,
            limit=request.limit,
            document_id=request.document_id,
            ef_search=settings.SEARCH_EF_SEARCH,
        )

        results: list[SearchResultItem] = []
        for chunk, filename, project_id, project_name, distance in rows:
            # pgvector 의 <=> 는 코사인 거리(0~2)다. 사람이 읽기 쉬운 유사도로
            # 바꾼다. 정규화된 벡터에서 거리 0 = 유사도 1 이다.
            similarity = 1.0 - distance
            if request.min_similarity is not None and similarity < request.min_similarity:
                # 거리 오름차순이므로 여기부터는 전부 임계값 아래다.
                break
            results.append(
                SearchResultItem(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_filename=filename,
                    project_id=project_id,
                    project_name=project_name,
                    seq=chunk.seq,
                    page_number=chunk.page_number,
                    similarity=round(similarity, 6),
                    snippet=self._snippet(chunk.text),
                    char_count=chunk.char_count,
                    content_start=chunk.content_start,
                    content_end=chunk.content_end,
                )
            )

        took_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "의미 검색 user_id=%s 범위=%s 결과=%d 모델=%s %dms",
            user_id,
            scope,
            len(results),
            embedded.model,
            took_ms,
        )
        return SearchResponse(
            query=request.query,
            searched_project_ids=scope,
            embedding_model=embedded.model,
            took_ms=took_ms,
            total=len(results),
            results=results,
        )

    def explain(self, user_id: int, request: SearchRequest) -> str:
        """검색 실행계획을 돌려준다. 리비전 0014 검증용이다."""
        scope = self._resolve_scope(user_id, request.project_ids)
        if not scope:
            return "검색 범위가 비어 있다 (멤버인 프로젝트가 없음)."
        embedded = self._embedder.embed_query(request.query.strip())
        if not embedded.vectors:
            return "질의 임베딩이 비어 있어 계획을 낼 수 없다."
        return self._chunks.explain_search(
            project_ids=scope,
            vector=list(embedded.vectors[0]),
            embedding_model=embedded.model,
            limit=request.limit,
            ef_search=settings.SEARCH_EF_SEARCH,
        )

    # --- 내부 ---------------------------------------------------------------

    def _resolve_scope(self, user_id: int, requested: list[int] | None) -> list[int]:
        """검색할 프로젝트 id 목록을 정한다.

        요청이 None 이면 내가 멤버인 전체다. 목록을 주면 그 전부가 내 멤버십에
        있어야 하고, 하나라도 아니면 PROJECT_NOT_FOUND 로 막는다.

        "권한이 없다"(403)가 아니라 "없다"(404)로 답하는 이유는 기존
        get_project_access 와 같다 — 남의 프로젝트가 존재한다는 사실 자체를
        알려주지 않는다. id 를 훑어서 어느 번호가 쓰이는지 알아내는 것을 막는다.
        """
        member_ids = [
            project.id for project, _member in self._projects.list_for_user(user_id)
        ]
        if requested is None:
            return sorted(member_ids)

        allowed = set(member_ids)
        # 중복을 없애고 순서를 고정한다. IN 목록에 같은 값이 여러 번 들어가는 것을
        # 막고, 응답의 searched_project_ids 가 매번 같은 순서로 나오게 한다.
        unique = sorted(set(requested))
        missing = [pid for pid in unique if pid not in allowed]
        if missing:
            logger.info(
                "멤버가 아닌 프로젝트를 검색 범위로 요청했다 user_id=%s 거부=%s",
                user_id,
                missing,
            )
            raise BusinessError(ErrorCode.PROJECT_NOT_FOUND)
        return unique

    def _empty(
        self,
        request: SearchRequest,
        scope: list[int],
        started: float,
        model: str = "",
    ) -> SearchResponse:
        return SearchResponse(
            query=request.query,
            searched_project_ids=scope,
            embedding_model=model or self._embedder.model_name,
            took_ms=int((time.perf_counter() - started) * 1000),
            total=0,
            results=[],
        )

    @staticmethod
    def _snippet(text: str) -> str:
        """원문 인용을 만든다 (RAG-08).

        청크는 최대 480토큰이라 그대로 담으면 목록 응답이 커진다. 앞부분을 잘라
        담고, 잘렸는지는 프론트가 char_count 와 비교해 판단한다.

        의미 검색은 질의 글자가 본문에 없어도 걸리는 것이 목적이라(RAG-04),
        키워드 하이라이트처럼 "질의가 나온 자리"를 잡을 수 없다. 그래서 앞부분을
        준다. 청크 맨 앞에는 제목이 오게 청킹해 뒀으므로(chunking.py 의 겹침
        처리) 앞부분이 그 청크의 주제를 가장 잘 나타낸다.
        """
        limit = settings.SEARCH_SNIPPET_CHARS
        # 줄바꿈을 공백으로 눌러 한 줄로 만든다. 프론트에서 목록으로 보여주므로
        # 원문 줄바꿈을 유지하면 카드 높이가 들쭉날쭉해진다.
        flat = " ".join(text.split())
        if len(flat) <= limit:
            return flat
        cut = flat[:limit]
        # 단어 중간에서 끊기지 않게 마지막 공백까지 되돌린다. 한국어는 공백이
        # 적어 되돌릴 자리가 없을 수 있으니, 너무 많이 깎이면 그대로 둔다.
        space = cut.rfind(" ")
        if space > limit * 0.7:
            cut = cut[:space]
        return cut + "…"
