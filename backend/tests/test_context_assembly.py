# =============================================================================
# 이 파일의 책임: 프롬프트 컨텍스트 조립(RAG-002-1)을 DB·LLM 없이 검증한다.
#   완료 판정이 "긴 문서에서도 컨텍스트 한도를 넘지 않는다" 이므로
#   **예산을 넘지 않는 것**이 가장 중요한 검사다.
#
#   검사하는 것
#     ① 예산을 넘지 않는가 (완료 판정)
#     ② 겹침으로 들어온 중복 문장을 걸러내는가 (핵심 목적)
#     ③ 예산에 안 들어가는 청크를 건너뛰고 다음 것을 담는가
#     ④ 첫 근거가 예산보다 크면 잘라서라도 담는가
#     ⑤ 검색 순서를 지키는가
#     ⑥ 출처 머리말이 붙는가 (CHAT-001 의 근거 인용 전제)
#
# 다른 파일과의 관계: app/services/context_assembly.py
#   순수 로직이라 MagicMock 도 필요 없다.
#
# Spring 비교: 의존성 없는 도메인 서비스의 단위 테스트.
# =============================================================================

from app.services.chunking import CHARS_PER_TOKEN
from app.services.context_assembly import (
    ContextChunk,
    assemble_context,
    split_sentences,
)


def chunk(chunk_id, text, *, seq=None, document_id=1, filename="입찰공고.pdf"):
    return ContextChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        filename=filename,
        seq=seq if seq is not None else chunk_id,
        text=text,
    )


def long_text(sentences: int) -> str:
    """서로 다른 문장으로 긴 본문을 만든다.

    같은 문장을 반복하면 **중복 제거가 걸러내서** 길어지지 않는다. 예산 초과를
    검사하려면 문장이 서로 달라야 한다 — 처음에 반복으로 만들어 테스트가 틀렸다.
    """
    return " ".join(
        f"{i}번째 항목에 대한 서로 다른 설명이 여기에 들어 있다." for i in range(sentences)
    )


def tokens_of(text: str) -> int:
    """테스트가 기대값을 손으로 세지 않게 한다. 도구와 같은 자를 쓴다."""
    return max(1, int(len(text) / CHARS_PER_TOKEN + 0.999))


# --- ① 예산을 넘지 않는다 (완료 판정) ---------------------------------------


def test_never_exceeds_budget():
    chunks = [chunk(i, f"조각 {i} 이다. " + long_text(20)) for i in range(1, 11)]
    for budget in (1, 10, 50, 100, 300, 1000):
        out = assemble_context(chunks, budget_tokens=budget)
        assert out.used_tokens <= budget, (
            f"예산 {budget} 을 넘겼다: {out.used_tokens}"
        )
        assert tokens_of(out.text) <= budget, "조립된 본문이 예산을 넘는다"


def test_zero_budget_returns_empty():
    out = assemble_context([chunk(1, "내용이다.")], budget_tokens=0)
    assert out.text == ""
    assert out.evidences == []
    assert out.used_tokens == 0


def test_negative_budget_does_not_raise():
    """설정을 잘못 넣었다고 요청을 실패시킬 이유가 없다."""
    out = assemble_context([chunk(1, "내용이다.")], budget_tokens=-5)
    assert out.text == ""
    assert out.budget_tokens == 0


def test_empty_input():
    out = assemble_context([], budget_tokens=100)
    assert out.text == ""
    assert out.used_tokens == 0


# --- ② 겹침 중복 제거 (핵심 목적) -------------------------------------------


def test_overlap_sentence_is_dropped():
    """청킹이 넣은 겹침 때문에 같은 문장이 두 청크에 있다. 한 번만 담아야 한다."""
    shared = "준공 검사 완료 후 30일 이내에 지급한다."
    a = chunk(1, f"제 2 장 계약 및 대금. {shared}", seq=0)
    b = chunk(2, f"{shared} 선금은 계약 금액의 70퍼센트 범위에서 지급할 수 있다.", seq=1)

    out = assemble_context([a, b], budget_tokens=1000)

    assert out.text.count(shared) == 1, f"중복이 남았다:\n{out.text}"
    assert out.dropped_sentences == 1
    assert out.evidences[1].dropped_sentences == 1
    # 뒤 청크의 고유 내용은 살아 있어야 한다.
    assert "선금은" in out.text


def test_overlap_removal_saves_tokens():
    """중복을 걸러내면 같은 자료가 더 적은 토큰을 쓴다 — 이 기능의 존재 이유다.

    근거 개수로 세지 않고 **토큰 절약분**을 직접 본다. 개수는 청크 크기와 예산의
    조합에 따라 흔들리지만, 절약분은 중복이 있으면 반드시 0 보다 크다.
    """
    overlap = "준공 검사 완료 후 30일 이내에 지급한다."
    chunks = [
        chunk(i, f"{overlap} 조각 {i} 에만 있는 고유한 설명이 이어진다.", seq=i)
        for i in range(1, 6)
    ]
    # 겹침을 그대로 두면 얼마나 들까 — 청크마다 따로 조립해 더한 값.
    naive = sum(
        assemble_context([c], budget_tokens=10000).used_tokens for c in chunks
    )
    out = assemble_context(chunks, budget_tokens=10000)

    assert out.dropped_sentences == 4, out.dropped_sentences
    assert out.used_tokens < naive, (
        f"중복 제거가 토큰을 아끼지 못했다: {out.used_tokens} vs {naive}"
    )
    # 겹침 문장은 딱 한 번만 남아야 한다.
    assert out.text.count(overlap) == 1
    # 고유 내용은 다섯 개 다 살아 있어야 한다.
    for i in range(1, 6):
        assert f"조각 {i} 에만" in out.text


def test_repeated_sentence_inside_one_chunk_is_deduped():
    """한 청크 안의 반복도 걸러낸다. 표의 같은 행이 여러 번 나오는 문서가 있다."""
    line = "청렴계약 이행을 확약한다."
    out = assemble_context(
        [chunk(1, f"{line} {line} {line} 그 밖의 내용이다.")], budget_tokens=1000
    )
    assert out.text.count(line) == 1
    assert out.dropped_sentences == 2
    assert "그 밖의 내용이다" in out.text


def test_all_duplicate_chunk_is_skipped_without_using_budget():
    same = "청렴계약 이행을 확약한다."
    out = assemble_context(
        [chunk(1, same, seq=0), chunk(2, same, seq=1)], budget_tokens=1000
    )
    assert len(out.evidences) == 1
    # 예산을 쓰지 않았으므로 '예산 때문에 건너뜀' 으로 세지 않는다.
    assert out.skipped_for_budget == 0


def test_whitespace_difference_is_still_duplicate():
    """청크 경계에서 개행이 공백으로 바뀌어도 같은 문장으로 봐야 한다."""
    out = assemble_context(
        [
            chunk(1, "대금은  준공 후\n30일 이내에 지급한다.", seq=0),
            chunk(2, "대금은 준공 후 30일 이내에 지급한다. 선금은 없다.", seq=1),
        ],
        budget_tokens=1000,
    )
    assert out.dropped_sentences == 1
    assert "선금은 없다" in out.text


# --- ③ 예산에 안 들어가면 건너뛰고 다음 것을 본다 --------------------------


def test_big_chunk_is_skipped_and_smaller_one_fits():
    """멈추지 않고 다음 것을 본다. 뒤에 작은 청크가 들어갈 수 있다."""
    small_first = chunk(1, "짧은 근거다.", seq=0)
    huge = chunk(2, "긴 " * 400, seq=1)
    small_after = chunk(3, "뒤에 있는 짧은 근거다.", seq=2)

    out = assemble_context([small_first, huge, small_after], budget_tokens=60)

    ids = [e.chunk_id for e in out.evidences]
    assert 2 not in ids, "예산을 넘는 청크가 담겼다"
    assert ids == [1, 3], f"작은 청크를 건너뛰었다: {ids}"
    assert out.skipped_for_budget == 1


def test_max_evidences_caps_count():
    chunks = [chunk(i, f"근거 {i} 이다.", seq=i) for i in range(1, 8)]
    out = assemble_context(chunks, budget_tokens=10000, max_evidences=3)
    assert len(out.evidences) == 3
    assert out.skipped_for_budget == 4


# --- ④ 첫 근거만 예외로 자른다 ----------------------------------------------


def test_first_evidence_is_truncated_rather_than_dropped():
    """첫 청크가 예산보다 크면 아무것도 못 담게 된다. 그때는 잘라서라도 담는다."""
    out = assemble_context([chunk(1, long_text(60))], budget_tokens=40)
    assert out.truncated is True
    assert len(out.evidences) == 1
    assert out.used_tokens <= 40
    assert out.evidences[0].text  # 빈 근거를 담지 않는다


def test_later_evidence_is_not_truncated():
    """두 번째부터는 자르지 않는다 — 잘린 근거는 원문에서 되찾을 수 없다."""
    out = assemble_context(
        [chunk(1, "짧은 근거다.", seq=0), chunk(2, long_text(60), seq=1)],
        budget_tokens=40,
    )
    assert out.truncated is False
    assert [e.chunk_id for e in out.evidences] == [1]
    assert out.skipped_for_budget == 1


# --- ⑤ 검색 순서를 지킨다 ---------------------------------------------------


def test_keeps_search_order():
    """관련도 순을 문서·조각 번호로 다시 정렬하지 않는다."""
    chunks = [
        chunk(30, "가장 관련 높은 근거다.", seq=29, document_id=9, filename="나중문서.pdf"),
        chunk(1, "그다음 근거다.", seq=0, document_id=1, filename="첫문서.pdf"),
    ]
    out = assemble_context(chunks, budget_tokens=1000)
    assert [e.chunk_id for e in out.evidences] == [30, 1]
    assert out.text.index("가장 관련 높은") < out.text.index("그다음")


# --- ⑥ 출처 머리말 ----------------------------------------------------------


def test_source_header_has_filename_and_human_seq():
    """LLM 이 출처를 인용할 수 있어야 하고, 사람이 원문에서 되찾을 수 있어야 한다."""
    out = assemble_context(
        [chunk(7, "대금 지급 조건이다.", seq=4, filename="입찰공고.pdf")],
        budget_tokens=1000,
    )
    # seq 는 0부터지만 사람에게는 1부터 보여준다 (화면과 같은 규칙).
    assert "[근거 1] 입찰공고.pdf · 조각 5번" in out.text


def test_header_index_counts_only_included_evidences():
    """중복으로 건너뛴 청크가 번호를 먹으면 근거 번호에 구멍이 생긴다."""
    same = "같은 문장이다."
    out = assemble_context(
        [
            chunk(1, f"첫째 고유 내용이다. {same}", seq=0),
            chunk(2, same, seq=1),
            chunk(3, "셋째 고유 내용이다.", seq=2),
        ],
        budget_tokens=1000,
    )
    assert "[근거 1]" in out.text
    assert "[근거 2]" in out.text
    assert "[근거 3]" not in out.text
    assert len(out.evidences) == 2


# --- 문장 쪼개기 ------------------------------------------------------------


def test_split_sentences_uses_korean_endings():
    """청킹과 같은 규칙이다 — '다' 로 끝나는 한국어 문장을 경계로 본다."""
    parts = split_sentences("대금은 30일 이내에 지급한다 선금은 없다")
    assert len(parts) == 2


def test_split_sentences_drops_blanks():
    assert split_sentences("  \n\n  ") == []


def test_remaining_tokens():
    out = assemble_context([chunk(1, "짧은 근거다.")], budget_tokens=100)
    assert out.remaining_tokens == 100 - out.used_tokens
