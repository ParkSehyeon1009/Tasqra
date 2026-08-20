# =============================================================================
# 이 파일의 책임: 키워드 검색(SRH-003)을 DB 없이 검증한다.
#   검사하는 것 셋 —
#     ① like_pattern 이 와일드카드를 죽이는가 (죽이지 않으면 조건이 사라진다)
#     ② _keyword_snippet 의 offset 이 snippet 과 정확히 맞는가
#     ③ 서비스가 범위·권한·최소 길이를 지키는가
#
# 다른 파일과의 관계:
#   app/repositories/chunk_repository.py 의 like_pattern (순수 함수)
#   app/services/search_service.py 의 SearchService (MagicMock 으로 조립)
#
# DB 를 띄우지 않는다. 레포 관례를 따른다 —
#   MagicMock + SimpleNamespace 로 서비스만 조립한다(test_document_list_queries.py).
#   ILIKE 가 실제로 ix_chunk_text_trgm 를 타는지는 여기서 알 수 없다.
#   그건 DB 가 필요하고 EXPLAIN 으로 따로 확인한다.
#
# Spring 비교: @SpringBootTest 가 아니라 Mockito 로 의존성을 주입한
#   서비스 단위 테스트다.
# =============================================================================

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.repositories.chunk_repository import like_pattern
from app.schemas.search import KeywordSearchRequest
from app.services.search_service import SearchService


# --- ① like_pattern — 와일드카드를 죽인다 -----------------------------------


def test_like_pattern_kills_wildcards():
    # % 를 그대로 두면 "100" 으로 시작하는 것 전부가 걸린다.
    assert like_pattern("100%") == "%100\\%%"
    # _ 는 한 글자 와일드카드다.
    assert like_pattern("제_조") == "%제\\_조%"
    # 역슬래시를 먼저 바꿔야 우리가 넣은 이스케이프를 다시 이스케이프하지 않는다.
    assert like_pattern("a\\b") == "%a\\\\b%"
    # 평범한 검색어는 감싸기만 한다.
    assert like_pattern("제2026-403호") == "%제2026-403호%"


def test_like_pattern_only_wildcard_does_not_match_everything():
    """검색어가 '%' 하나여도 조건이 사라지지 않아야 한다."""
    # 이스케이프가 없으면 "%%%" 가 되어 모든 행이 걸린다.
    assert like_pattern("%") == "%\\%%"


# --- ② _keyword_snippet — offset 이 snippet 과 맞는다 ------------------------


def _check_offset(text: str, term: str) -> tuple[str, int | None]:
    """돌려준 offset 자리에 정말 검색어가 있는지 확인한다."""
    snippet, offset = SearchService._keyword_snippet(text, term)
    if offset is not None:
        found = snippet[offset : offset + len(term)]
        assert found.lower() == term.lower(), (
            f"offset 이 어긋났다: snippet[{offset}:] = {found!r}, 기대 {term!r}"
        )
    return snippet, offset


def test_keyword_snippet_short_text_returns_whole():
    snippet, offset = _check_offset("계약금액은 1억원이다", "계약금액")
    assert snippet == "계약금액은 1억원이다"
    assert offset == 0


def test_keyword_snippet_flattens_whitespace_before_locating():
    """줄바꿈을 누른 뒤에 찾아야 offset 이 snippet 과 맞는다.

    누르기 전에 찾으면 글자 수가 줄면서 위치가 어긋난다.
    """
    text = "제1조   목적\n\n이 계약의   계약금액은 1억원이다"
    snippet, offset = _check_offset(text, "계약금액")
    # 연속 공백이 한 칸으로 눌렸다.
    assert "   " not in snippet
    assert offset is not None


def test_keyword_snippet_centers_match_and_marks_ellipsis():
    """긴 본문에서는 매치를 가운데 두고 앞뒤에 … 를 붙인다."""
    text = "가" * 500 + "계약금액" + "나" * 500
    snippet, offset = _check_offset(text, "계약금액")
    assert snippet.startswith("…")
    assert snippet.endswith("…")
    # 앞의 "…" 만큼 offset 이 밀려 있어야 한다. _check_offset 이 이미 확인했다.
    assert offset is not None and offset > 0


def test_keyword_snippet_match_at_start_has_no_leading_ellipsis():
    text = "계약금액은 " + "가" * 500
    snippet, offset = _check_offset(text, "계약금액")
    assert not snippet.startswith("…")
    assert offset == 0
    assert snippet.endswith("…")


def test_keyword_snippet_match_at_end_keeps_window_length():
    text = "가" * 500 + "계약금액"
    snippet, offset = _check_offset(text, "계약금액")
    assert snippet.startswith("…")
    assert not snippet.endswith("…")
    assert offset is not None


def test_keyword_snippet_is_case_insensitive():
    snippet, offset = _check_offset("이것은 SI 사업이다", "si")
    assert offset is not None
    assert snippet[offset : offset + 2] == "SI"


def test_keyword_snippet_not_found_still_returns_text():
    """조회가 ILIKE 로 걸러 왔어도, 줄바꿈이 검색어에 걸치면 못 찾을 수 있다.

    그때도 스니펫은 주고 offset 만 None 이다 — 강조만 못 한다.
    """
    snippet, offset = SearchService._keyword_snippet("가나다라마", "없는말")
    assert offset is None
    assert snippet == "가나다라마"


# --- ② 매치 횟수 -------------------------------------------------------------


def test_count_occurrences_ignores_case():
    assert SearchService._count_occurrences("SI 사업 si 사업", "si") == 2


def test_count_occurrences_zero_when_absent():
    assert SearchService._count_occurrences("가나다", "라마") == 0


def test_count_occurrences_empty_term_is_zero():
    """빈 검색어에 str.count 는 글자수+1 을 준다. 그걸 그대로 쓰면 안 된다."""
    assert SearchService._count_occurrences("가나다", "") == 0


# --- ③ 서비스 — 범위·권한·최소 길이 ----------------------------------------


def _service(member_project_ids=(1,), rows=()):
    db = MagicMock()
    chunks = MagicMock()
    projects = MagicMock()
    embedder = MagicMock()
    embedder.model_name = "dragonkue/BGE-m3-ko"
    projects.list_for_user.return_value = [
        (SimpleNamespace(id=pid), SimpleNamespace(role="OWNER"))
        for pid in member_project_ids
    ]
    chunks.search_by_keyword.return_value = list(rows)
    return SearchService(db, chunks, projects, embedder), chunks, embedder


def _chunk(text="계약금액은 1억원이다", **kw):
    base = dict(
        id=11,
        document_id=22,
        seq=3,
        page_number=1,
        text=text,
        char_count=len(text),
        content_start=100,
        content_end=100 + len(text),
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_keyword_too_short_is_rejected():
    service, chunks, _ = _service()
    with pytest.raises(BusinessError) as err:
        service.search_keyword(1, KeywordSearchRequest(query="가", project_ids=[1]))
    assert err.value.error_code is ErrorCode.KEYWORD_TOO_SHORT
    # 검색을 시도조차 하지 않아야 한다.
    chunks.search_by_keyword.assert_not_called()


def test_whitespace_only_query_is_rejected():
    """Pydantic 은 min_length=1 만 보므로 공백 한 칸은 통과한다. 서비스가 막는다."""
    service, chunks, _ = _service()
    with pytest.raises(BusinessError) as err:
        service.search_keyword(1, KeywordSearchRequest(query="   ", project_ids=[1]))
    assert err.value.error_code is ErrorCode.KEYWORD_TOO_SHORT
    chunks.search_by_keyword.assert_not_called()


def test_non_member_project_is_404_not_403():
    """남의 프로젝트 존재 자체를 알려주지 않는다. 의미 검색과 같은 규칙이다."""
    service, chunks, _ = _service(member_project_ids=(1,))
    with pytest.raises(BusinessError) as err:
        service.search_keyword(
            1, KeywordSearchRequest(query="계약금액", project_ids=[999])
        )
    assert err.value.error_code is ErrorCode.PROJECT_NOT_FOUND
    assert err.value.error_code.status_code == 404
    chunks.search_by_keyword.assert_not_called()


def test_no_membership_returns_empty_not_error():
    service, chunks, _ = _service(member_project_ids=())
    response = service.search_keyword(1, KeywordSearchRequest(query="계약금액"))
    assert response.total == 0
    assert response.results == []
    assert response.searched_project_ids == []
    chunks.search_by_keyword.assert_not_called()


def test_keyword_search_fills_match_fields():
    text = "제1조 목적. 이 계약의 계약금액은 1억원이며 계약금액 변경은 협의한다."
    service, chunks, _ = _service(rows=[(_chunk(text), "입찰공고.pdf", 1, "우리사업", 0.85)])

    response = service.search_keyword(
        1, KeywordSearchRequest(query="계약금액", project_ids=[1])
    )

    assert response.total == 1
    item = response.results[0]
    assert item.match_kind == "keyword"
    # 본문에 두 번 나온다.
    assert item.match_count == 2
    # offset 자리에 검색어가 있어야 한다.
    assert item.snippet[item.match_offset : item.match_offset + 4] == "계약금액"
    # 기존 필드도 그대로 채워진다.
    assert item.chunk_id == 11
    assert item.document_filename == "입찰공고.pdf"
    assert item.project_name == "우리사업"
    assert item.content_start == 100
    assert item.similarity == 0.85


def test_keyword_search_passes_current_model_to_repository():
    """모델 조건을 빼면 같은 본문이 모델별로 중복해서 나온다."""
    service, chunks, embedder = _service(rows=[])
    service.search_keyword(
        1, KeywordSearchRequest(query="계약금액", project_ids=[1], limit=5)
    )
    kwargs = chunks.search_by_keyword.call_args.kwargs
    assert kwargs["embedding_model"] == embedder.model_name
    assert kwargs["project_ids"] == [1]
    assert kwargs["limit"] == 5
    # 앞뒤 공백을 떼고 넘긴다.
    assert kwargs["term"] == "계약금액"


def test_keyword_search_does_not_embed():
    """임베딩을 만들지 않아야 한다 — 모델 서버 없이도 동작해야 하기 때문이다."""
    service, _, embedder = _service(rows=[])
    service.search_keyword(1, KeywordSearchRequest(query="계약금액", project_ids=[1]))
    embedder.embed_query.assert_not_called()
    embedder.embed_documents.assert_not_called()


def test_keyword_search_trims_query_before_search():
    service, chunks, _ = _service(rows=[])
    service.search_keyword(
        1, KeywordSearchRequest(query="  계약금액  ", project_ids=[1])
    )
    assert chunks.search_by_keyword.call_args.kwargs["term"] == "계약금액"
