# =============================================================================
# 이 파일의 책임: 하이브리드 검색(SRH-004)의 RRF 결합을 DB 없이 검증한다.
#   검사하는 것 —
#     ① RRF 산수가 맞는가 (순위는 1부터 · Σ 1/(k+순위))
#     ② 두 방식에 모두 걸린 결과가 위로 오는가
#     ③ 같은 청크가 중복으로 나오지 않는가
#     ④ 검색어가 짧으면 키워드만 건너뛰고 오류를 내지 않는가
#     ⑤ 순서가 결정론적인가 (같은 입력에 같은 순서)
#
# 다른 파일과의 관계:
#   app/services/search_service.py 의 SearchService.search_hybrid · _fuse
#   app/schemas/search.py 의 HybridSearchRequest
#
# DB 를 띄우지 않는다. MagicMock 으로 리포지토리를 흉내낸다
# (test_document_list_queries.py · test_search_keyword.py 와 같은 방식).
#
# Spring 비교: Mockito 로 Repository 를 스텁하고 Service 만 단위 검증하는 것.
# =============================================================================

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.schemas.search import HybridSearchRequest
from app.services.search_service import SearchService

K = settings.SEARCH_HYBRID_RRF_K

# fused_score 는 응답에 8자리로 끊어 담긴다(_fuse). 그래서 비교 허용오차가
# 반올림 오차(최대 5e-9)보다 커야 한다. 1e-9 로 두면 코드가 맞아도 실패한다 —
# 실제로 한 번 그렇게 틀렸다.
#
# 8자리가 충분한 근거는 아래 test_eight_decimals_distinguish_adjacent_ranks 가
# 검사한다. 인접 순위의 점수 차가 2.6e-4 라 해상도의 26,000배다.
RRF_TOL = 1e-8


def _chunk(chunk_id, *, text="계약금액은 1억원이다", seq=None, document_id=22):
    return SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        seq=seq if seq is not None else chunk_id,
        page_number=1,
        text=text,
        char_count=len(text),
        content_start=100,
        content_end=100 + len(text),
    )


def _row(chunk, score):
    """리포지토리가 돌려주는 모양: (청크, 파일명, 프로젝트id, 프로젝트명, 점수)"""
    return (chunk, "입찰공고.pdf", 1, "우리사업", score)


def _service(*, vector_rows=(), keyword_rows=(), member_ids=(1,), vectors=((0.1,),)):
    db = MagicMock()
    chunks = MagicMock()
    projects = MagicMock()
    embedder = MagicMock()
    embedder.model_name = "dragonkue/BGE-m3-ko"
    embedder.embed_query.return_value = SimpleNamespace(
        vectors=list(vectors), model="dragonkue/BGE-m3-ko", dimension=1
    )
    projects.list_for_user.return_value = [
        (SimpleNamespace(id=p), SimpleNamespace(role="OWNER")) for p in member_ids
    ]
    chunks.search_by_vector.return_value = list(vector_rows)
    chunks.search_by_keyword.return_value = list(keyword_rows)
    return SearchService(db, chunks, projects, embedder), chunks, embedder


def _ask(service, query="계약금액", **kw):
    return service.search_hybrid(
        1, HybridSearchRequest(query=query, project_ids=[1], **kw)
    )


# --- ① RRF 산수 --------------------------------------------------------------


def test_rrf_score_uses_rank_starting_at_one():
    """1등의 점수는 1/(k+1) 이어야 한다. 0부터 세면 1/k 가 되어 정의가 어긋난다."""
    service, _, _ = _service(vector_rows=[_row(_chunk(1), 0.2)])
    item = _ask(service).results[0]
    assert item.vector_rank == 1
    assert item.fused_score == pytest.approx(1 / (K + 1), abs=RRF_TOL)


def test_rrf_score_decreases_with_rank():
    service, _, _ = _service(
        vector_rows=[_row(_chunk(1), 0.1), _row(_chunk(2), 0.2), _row(_chunk(3), 0.3)]
    )
    scores = [r.fused_score for r in _ask(service).results]
    assert scores == sorted(scores, reverse=True)
    assert scores[1] == pytest.approx(1 / (K + 2), abs=RRF_TOL)


def test_rrf_sums_both_legs():
    """양쪽에 걸리면 두 항이 더해진다."""
    c = _chunk(1)
    service, _, _ = _service(vector_rows=[_row(c, 0.2)], keyword_rows=[_row(c, 0.9)])
    item = _ask(service).results[0]
    assert item.fused_score == pytest.approx(1 / (K + 1) + 1 / (K + 1), abs=RRF_TOL)


def test_eight_decimals_distinguish_adjacent_ranks():
    """응답의 8자리 반올림이 순위를 뭉개지 않는지 검사한다.

    fused_score 를 끊어 담는 것은 표시용이고 정렬은 원본으로 한다. 그래도 화면이
    이 값으로 순서를 다시 매길 수 있으므로, **끊은 뒤에도 인접 순위가 구별되어야**
    한다. 1/(k+1) - 1/(k+2) = 2.6e-4 로 해상도 1e-8 의 26,000배다.
    """
    service, _, _ = _service(
        vector_rows=[_row(_chunk(i), 0.01 * i) for i in range(1, 11)]
    )
    scores = [r.fused_score for r in _ask(service).results]
    # 끊은 값끼리도 전부 서로 다르고 내림차순이어야 한다.
    assert len(set(scores)) == len(scores), f"끊어서 같아진 값이 있다: {scores}"
    assert scores == sorted(scores, reverse=True)
    # 가장 가까운 두 값의 차이가 해상도보다 훨씬 크다는 것을 수치로 남긴다.
    gaps = [a - b for a, b in zip(scores, scores[1:])]
    assert min(gaps) > 1e-6, f"인접 간격이 너무 좁다: {min(gaps)}"


def test_ordering_uses_unrounded_score():
    """정렬이 반올림된 값이 아니라 원본으로 되는지 확인한다.

    양쪽에 걸린 것(2/(k+1))과 한쪽 1등(1/(k+1))은 차이가 크지만, 순서가 점수로
    정해진다는 것 자체를 고정해 둔다. 정렬 키를 fused_score(끊은 값)로 바꾸면
    이 테스트는 통과하겠지만, 위 테스트가 간격을 지키므로 함께 보면 안전하다.
    """
    both, single = _chunk(1, seq=9), _chunk(2, seq=1)
    service, _, _ = _service(
        vector_rows=[_row(single, 0.1), _row(both, 0.2)],
        keyword_rows=[_row(both, 0.9)],
    )
    results = _ask(service).results
    # seq 가 큰 both 가 앞에 온다 -> tie-break 가 아니라 점수로 정렬됐다는 뜻이다.
    assert [r.chunk_id for r in results] == [both.id, single.id]
    assert results[0].fused_score > results[1].fused_score


# --- ② 양쪽에 걸린 것이 위로 온다 -------------------------------------------


def test_result_in_both_legs_outranks_single_leg_first_place():
    """한쪽 1등보다 양쪽 3등·5등이 위여야 한다. 두 방식이 동의하는 쪽이 믿을 만하다."""
    only_vector = _chunk(1)                      # 벡터 1등
    both = _chunk(2)                             # 벡터 3등 · 키워드 5등
    service, _, _ = _service(
        vector_rows=[_row(only_vector, 0.1), _row(_chunk(9), 0.2), _row(both, 0.3)],
        keyword_rows=[
            _row(_chunk(11), 0.9), _row(_chunk(12), 0.9), _row(_chunk(13), 0.9),
            _row(_chunk(14), 0.9), _row(both, 0.8),
        ],
    )
    results = _ask(service).results
    assert results[0].chunk_id == both.id
    assert results[0].match_kind == "both"
    assert results[0].vector_rank == 3
    assert results[0].keyword_rank == 5


def test_match_kind_labels_each_source():
    v, kw, both = _chunk(1), _chunk(2), _chunk(3)
    service, _, _ = _service(
        vector_rows=[_row(v, 0.1), _row(both, 0.2)],
        keyword_rows=[_row(both, 0.9), _row(kw, 0.8)],
    )
    kinds = {r.chunk_id: r.match_kind for r in _ask(service).results}
    assert kinds == {1: "vector", 2: "keyword", 3: "both"}


# --- ③ 중복 제거 -------------------------------------------------------------


def test_same_chunk_appears_once():
    c = _chunk(1)
    service, _, _ = _service(vector_rows=[_row(c, 0.2)], keyword_rows=[_row(c, 0.9)])
    results = _ask(service).results
    assert len(results) == 1
    assert [r.chunk_id for r in results] == [1]


def test_limit_is_applied_after_fusion():
    """자르는 것은 합친 뒤여야 한다. 먼저 자르면 한쪽에만 걸린 정답이 사라진다."""
    service, _, _ = _service(
        vector_rows=[_row(_chunk(i), 0.1 * i) for i in range(1, 6)],
        keyword_rows=[_row(_chunk(i), 0.9) for i in range(6, 11)],
    )
    response = _ask(service, limit=3)
    assert response.total == 3
    assert len(response.results) == 3


# --- ④ 짧은 검색어 — 키워드만 건너뛴다 -------------------------------------


def test_short_query_skips_keyword_leg_without_error():
    """키워드 검색은 1글자를 막지만, 하이브리드는 의미 검색으로 답해야 한다."""
    service, chunks, _ = _service(vector_rows=[_row(_chunk(1), 0.2)])
    response = service.search_hybrid(
        1, HybridSearchRequest(query="가", project_ids=[1])
    )
    chunks.search_by_keyword.assert_not_called()
    chunks.search_by_vector.assert_called_once()
    assert response.total == 1
    assert response.results[0].match_kind == "vector"


def test_long_query_uses_both_legs():
    service, chunks, _ = _service(vector_rows=[_row(_chunk(1), 0.2)])
    _ask(service, query="계약금액")
    chunks.search_by_vector.assert_called_once()
    chunks.search_by_keyword.assert_called_once()


def test_empty_embedding_still_returns_keyword_results():
    """모델 서버가 죽어 임베딩이 비어도 키워드로는 찾아야 한다."""
    service, chunks, embedder = _service(keyword_rows=[_row(_chunk(1), 0.9)])
    embedder.embed_query.return_value = SimpleNamespace(
        vectors=[], model="dragonkue/BGE-m3-ko", dimension=1
    )
    response = _ask(service)
    chunks.search_by_vector.assert_not_called()
    assert response.total == 1
    assert response.results[0].match_kind == "keyword"


# --- ⑤ 결정론 · 권한 --------------------------------------------------------


def test_tie_is_broken_deterministically():
    """점수가 같으면 문서·순서로 고정한다. 흔들리면 회귀 테스트를 못 쓴다."""
    a = _chunk(1, document_id=5, seq=2)
    b = _chunk(2, document_id=5, seq=1)
    order = []
    for rows in ([_row(a, 0.5)], [_row(b, 0.5)]):
        other = [_row(b, 0.5)] if rows[0][0] is a else [_row(a, 0.5)]
        service, _, _ = _service(vector_rows=rows, keyword_rows=other)
        order.append([r.chunk_id for r in _ask(service).results])
    # 입력 순서를 바꿔도 같은 결과 순서가 나와야 한다 (seq 오름차순 -> 2 먼저).
    assert order[0] == order[1] == [2, 1]


def test_non_member_project_is_404():
    service, chunks, _ = _service(member_ids=(1,))
    with pytest.raises(BusinessError) as err:
        service.search_hybrid(
            1, HybridSearchRequest(query="계약금액", project_ids=[999])
        )
    assert err.value.error_code is ErrorCode.PROJECT_NOT_FOUND
    chunks.search_by_vector.assert_not_called()
    chunks.search_by_keyword.assert_not_called()


def test_no_membership_returns_empty():
    service, chunks, _ = _service(member_ids=())
    response = service.search_hybrid(1, HybridSearchRequest(query="계약금액"))
    assert response.total == 0
    chunks.search_by_vector.assert_not_called()


def test_candidates_overrides_default_depth():
    """후보 수가 리랭커 상한을 정하므로 실험할 수 있게 열어 두었다."""
    service, chunks, _ = _service(vector_rows=[])
    _ask(service, candidates=7)
    assert chunks.search_by_vector.call_args.kwargs["limit"] == 7
    assert chunks.search_by_keyword.call_args.kwargs["limit"] == 7


def test_default_depth_comes_from_settings():
    service, chunks, _ = _service(vector_rows=[])
    _ask(service)
    assert (
        chunks.search_by_vector.call_args.kwargs["limit"]
        == settings.SEARCH_HYBRID_CANDIDATES
    )


# --- 스니펫 · 유사도 담기 ---------------------------------------------------


def test_keyword_hit_gets_match_position_snippet():
    text = "제1조 목적. 이 계약의 계약금액은 1억원이며 계약금액 변경은 협의한다."
    c = _chunk(1, text=text)
    service, _, _ = _service(keyword_rows=[_row(c, 0.9)])
    item = _ask(service).results[0]
    assert item.match_count == 2
    assert item.snippet[item.match_offset : item.match_offset + 4] == "계약금액"


def test_vector_only_hit_has_no_match_fields():
    """벡터만으로 걸리면 질의 글자가 본문에 없을 수 있다. 강조할 자리가 없다."""
    service, _, _ = _service(vector_rows=[_row(_chunk(1, text="대금 지급 시기"), 0.2)])
    item = _ask(service).results[0]
    assert item.match_kind == "vector"
    assert item.match_count is None
    assert item.match_offset is None


def test_similarity_is_cosine_when_vector_hit():
    """거리 0.2 -> 유사도 0.8. RRF 점수가 아니라 해석 가능한 값을 담는다."""
    service, _, _ = _service(vector_rows=[_row(_chunk(1), 0.2)])
    item = _ask(service).results[0]
    assert item.similarity == pytest.approx(0.8, abs=1e-6)
    assert item.fused_score != item.similarity


def test_similarity_is_trigram_when_keyword_only():
    service, _, _ = _service(keyword_rows=[_row(_chunk(1), 0.8)])
    item = _ask(service).results[0]
    assert item.match_kind == "keyword"
    assert item.similarity == pytest.approx(0.8, abs=1e-6)
