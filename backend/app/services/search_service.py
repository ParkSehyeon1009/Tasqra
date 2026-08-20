# =============================================================================
# 이 파일의 책임: 의미 검색(SRH-001 = SRH-001)을 조립한다. 순서는 이렇다.
#     1. 검색 범위를 정한다 — 요청이 준 프로젝트 목록, 또는 내 멤버십 전체
#     2. 범위의 모든 프로젝트가 내 멤버십에 있는지 확인한다 (권한)
#     3. 질의를 벡터로 만든다
#     4. 그 범위 안에서 가까운 청크를 찾는다
#     5. 결과마다 출처와 원문 인용을 붙인다 (SRH-002-2 = SRH-002-2)
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
from app.schemas.search import (
    KeywordSearchRequest,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)

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

    def search_keyword(
        self, user_id: int, request: KeywordSearchRequest
    ) -> SearchResponse:
        """키워드 검색을 한다 (SRH-003).

        의미 검색과 다른 점은 셋이다.
          1. **임베딩을 만들지 않는다.** 그래서 모델 서버가 떠 있지 않아도 된다.
             `SYS-002-4` 임베딩 모델 서빙 경로가 미결인 상태에서도 이 기능은
             동작한다 — 다른 팀원이 실제 검색을 처음 돌려 볼 수 있는 경로다.
          2. **검색어 최소 길이를 검사한다.** 1글자는 어느 청크에나 있어서
             결과가 사실상 전체가 된다.
          3. **스니펫이 매치 자리를 보여준다.** 의미 검색은 질의 글자가 본문에
             없어도 걸리므로 앞부분을 주지만, 키워드는 위치를 알 수 있다.

        범위·권한 처리는 의미 검색과 **완전히 같다** — `_resolve_scope` 를 그대로
        쓴다. 따로 구현하면 한쪽만 고쳐졌을 때 권한 구멍이 생긴다.
        """
        started = time.perf_counter()
        term = request.query.strip()
        if len(term) < settings.SEARCH_KEYWORD_MIN_LENGTH:
            # 공백만 넣은 경우도 여기서 걸린다(strip 뒤 길이 0).
            raise BusinessError(ErrorCode.KEYWORD_TOO_SHORT)

        scope = self._resolve_scope(user_id, request.project_ids)
        if not scope:
            return self._empty_keyword(request, scope, started)

        # 임베딩을 만들지 않지만 모델 이름은 필요하다. 같은 문서를 여러 모델로
        # 청킹해 두면 같은 본문이 여러 행으로 있어서, 모델로 걸러야 결과에
        # 중복이 나오지 않는다. settings 대신 클라이언트의 이름을 쓰는 이유는
        # 의미 검색이 쓰는 값과 반드시 같아야 하기 때문이다.
        model = self._embedder.model_name

        rows = self._chunks.search_by_keyword(
            project_ids=scope,
            term=term,
            embedding_model=model,
            limit=request.limit,
            document_id=request.document_id,
        )

        results: list[SearchResultItem] = []
        for chunk, filename, project_id, project_name, score in rows:
            snippet, offset = self._keyword_snippet(chunk.text, term)
            results.append(
                SearchResultItem(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_filename=filename,
                    project_id=project_id,
                    project_name=project_name,
                    seq=chunk.seq,
                    page_number=chunk.page_number,
                    # 코사인 유사도가 아니라 트라이그램 낱말 유사도다. 어느
                    # 쪽인지는 match_kind 로 구분한다.
                    similarity=round(score, 6),
                    snippet=snippet,
                    char_count=chunk.char_count,
                    content_start=chunk.content_start,
                    content_end=chunk.content_end,
                    match_kind="keyword",
                    match_count=self._count_occurrences(chunk.text, term),
                    match_offset=offset,
                )
            )

        took_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "키워드 검색 user_id=%s 범위=%s 결과=%d 길이=%d %dms",
            user_id,
            scope,
            len(results),
            len(term),
            took_ms,
        )
        return SearchResponse(
            query=request.query,
            searched_project_ids=scope,
            embedding_model=model,
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

    def _empty_keyword(
        self, request: KeywordSearchRequest, scope: list[int], started: float
    ) -> SearchResponse:
        return SearchResponse(
            query=request.query,
            searched_project_ids=scope,
            embedding_model=self._embedder.model_name,
            took_ms=int((time.perf_counter() - started) * 1000),
            total=0,
            results=[],
        )

    @staticmethod
    def _count_occurrences(text: str, term: str) -> int:
        """검색어가 본문에 몇 번 나오는지 센다 (SRH-003).

        SQL 로도 셀 수 있지만(`length` 와 `replace` 조합) 파이썬으로 센다.
        본문이 이미 손에 있어서 왕복이 늘지 않고, DB 없이 테스트할 수 있다.

        대소문자를 무시한다 — 조회가 `ILIKE` 이므로 셈도 같은 기준이어야
        "1건 걸렸는데 0번 나온다" 같은 모순이 안 생긴다.

        `str.count` 는 겹치지 않게 센다("aa" 안의 "aaa" 는 1). LIKE 도 존재
        여부만 보므로 이 차이가 결과 집합을 바꾸지 않는다.
        """
        if not term:
            return 0
        return text.lower().count(term.lower())

    @staticmethod
    def _keyword_snippet(text: str, term: str) -> tuple[str, int | None]:
        """매치된 자리를 중심으로 원문 인용을 만든다 (SRH-003 + SRH-002-2).

        (스니펫, 스니펫 안에서 검색어가 시작하는 위치) 를 돌려준다.

        의미 검색의 `_snippet` 과 나눈 이유
          그쪽은 **앞부분 220자**를 준다. 질의 글자가 본문에 없어도 걸리므로
          "질의가 나온 자리" 가 없기 때문이다. 키워드는 자리가 있으니 그곳을
          보여주는 것이 근거로서 쓸모가 있다.

        먼저 공백을 누른 뒤에 위치를 찾는 순서가 중요하다
          `text` 에서 위치를 찾고 나서 공백을 누르면, 누르는 과정에서 글자 수가
          줄어들어 **위치가 어긋난다.** 그래서 누른 결과 안에서 찾는다.
          그러면 돌려주는 offset 이 돌려주는 snippet 과 항상 맞는다.

        ⚠ 이 offset 을 `content_start` 에 더해 원문 좌표로 쓸 수 없다. 공백을
        눌렀으므로 원문과 글자 수가 다르다. 원문 위 강조는 지금처럼 청크 단위
        (`content_start` ~ `content_end`)로 한다.

        찾지 못하면 offset 이 None 이다. 조회가 `ILIKE` 로 걸러 왔으니 보통은
        찾히지만, 검색어에 원문의 줄바꿈이 걸쳐 있으면(공백을 누르면서 한 칸이
        된 자리) 어긋날 수 있다. 그때도 스니펫은 돌려준다 — 강조만 못 한다.
        """
        limit = settings.SEARCH_KEYWORD_SNIPPET_CHARS
        flat = " ".join(text.split())
        at = flat.lower().find(term.lower())

        if at < 0:
            # 매치 자리를 못 찾았다. 의미 검색과 같은 방식으로 앞부분을 준다.
            head = flat if len(flat) <= limit else flat[:limit] + "…"
            return head, None

        if len(flat) <= limit:
            return flat, at

        # 검색어를 창의 가운데에 둔다. 앞뒤 맥락이 함께 보여야 근거가 된다.
        # 검색어가 창보다 길면 앞을 맞춘다(term 이 잘려도 시작은 보인다).
        room = max(limit - len(term), 0)
        start = max(at - room // 2, 0)
        end = min(start + limit, len(flat))
        # 뒤쪽이 짧아 창을 못 채우면 앞으로 밀어 길이를 유지한다.
        start = max(end - limit, 0)

        cut = flat[start:end]
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(flat) else ""
        # 앞에 "…" 를 붙이면 그만큼 offset 이 밀린다. 이걸 빼먹으면 강조가
        # 한 글자씩 어긋난다.
        return prefix + cut + suffix, (at - start) + len(prefix)

    @staticmethod
    def _snippet(text: str) -> str:
        """원문 인용을 만든다 (SRH-002-2).

        청크는 최대 480토큰이라 그대로 담으면 목록 응답이 커진다. 앞부분을 잘라
        담고, 잘렸는지는 프론트가 char_count 와 비교해 판단한다.

        의미 검색은 질의 글자가 본문에 없어도 걸리는 것이 목적이라(SRH-001),
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
