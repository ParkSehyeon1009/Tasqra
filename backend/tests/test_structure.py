import pytest

from app.extractors.structure import (
    detect_header_footer,
    detect_heading,
    normalize_repeated_text,
)


@pytest.mark.parametrize("text", [
    "제3조(계약의 목적)",
    "제 12 조 계약기간",
    "제2항 적용범위",
    "1. 사업개요",
    "1.2 추진배경",
    "1.2.3) 세부내용",
    "3) 제출서류",
    "가. 입찰참가자격",
    "나) 유의사항",
    "Ⅱ. 사업내용",
    "IV. 평가기준",
    "## 산출내역",
    # 실측(KISA 보고서 17건)에서 확인한 실제 제목
    "제 1 장",
    "3. 글로벌 사이버 위협 동향",
    # 끝 괄호를 떼도 문장 종결이 아니면 제목으로 남는다
    "1. 사업개요 (총괄)",
])
def test_heading_is_detected(text):
    assert detect_heading(text) is True


@pytest.mark.parametrize("text", [
    "5.8%", "9.3%", "38.5%", "3.14", "1.2", "12,345", "- 3 -", "( 3 )",
])
def test_numeric_only_lines_are_not_headings(text):
    """표·차트의 수치가 제목으로 잡히던 실측 오탐.

    _NUMBERED 가 "5.8%" 를 "번호 5 · 내용 8%" 로 읽는다. 숫자·기호만 있는 줄을
    먼저 걸러낸다.
    """
    assert detect_heading(text) is False


def test_trailing_parenthesis_does_not_hide_sentence_end():
    """끝 괄호가 종결 부호를 가리던 실측 오탐."""
    question = "3. 평소 사이버 보안에 대한 귀하의 관심은 어느 정도입니까? (조회 빈도 기준)"
    assert detect_heading(question) is False
    # 반대로 괄호를 떼도 문장이 아니면 제목으로 남는다
    assert detect_heading("1. 사업개요 (총괄)") is True


@pytest.mark.parametrize("text", [
    # 문장으로 끝나면 본문이다
    "1. 이 사업은 차세대 시스템을 구축한다.",
    "가. 제출서류는 아래와 같음",
    "1. 해당 사항 없음",
    "나. 별도 협의가 필요한 사항 있음",
    "제3조 계약상대자는 과업을 성실히 이행하여야 한다.",
    "2. 관련 서류를 제출함",
    # 글머리 기호는 목록 항목이다. 제목으로 보면 목록마다 단락이 끊긴다
    "■ 사업개요",
    "○ 추진배경",
    "▪ 세부내용",
    # 번호가 없으면 판정하지 않는다 (한계로 문서화된 동작)
    "사업 개요",
    "총칙",
    # 번호만 있고 내용이 없으면 표 안의 순번일 수 있다
    "1.",
    "가.",
    # 빈 값
    "",
    "   ",
])
def test_heading_is_not_detected(text):
    assert detect_heading(text) is False


def test_heading_length_limit_separates_title_from_body():
    title = "제3조(계약의 목적)"
    body = "제3조 " + "이 계약은 발주기관과 계약상대자가 과업을 수행하기 위한 것이다" * 2
    assert detect_heading(title) is True
    assert len(body) > 60
    assert detect_heading(body) is False


def test_heading_title_ending_with_yo_is_kept():
    """'개요' 처럼 '요' 로 끝나는 제목을 문장으로 오판하지 않는다."""
    assert detect_heading("1. 사업개요") is True
    assert detect_heading("2. 추진 개요") is True


def test_normalize_replaces_page_numbers():
    assert normalize_repeated_text("- 3 -") == normalize_repeated_text("- 4 -")
    assert normalize_repeated_text("3 / 24") == normalize_repeated_text("11 / 24")
    assert normalize_repeated_text("사업  계획서") == "사업 계획서"


def test_header_footer_found_when_repeated_in_band():
    pages = [
        [("사업계획서", 0.03), ("본문 첫째 줄", 0.5), ("- 1 -", 0.96)],
        [("사업계획서", 0.03), ("본문 둘째 줄", 0.5), ("- 2 -", 0.96)],
        [("사업계획서", 0.03), ("본문 셋째 줄", 0.5), ("- 3 -", 0.96)],
    ]
    found = detect_header_footer(pages)
    assert found == {(0, 0), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2)}


def test_header_footer_ignores_body_even_if_repeated():
    """가운데에 반복되는 문장이 있어도 대역 밖이면 잡지 않는다."""
    pages = [[("반복되는 본문", 0.5)] for _ in range(5)]
    assert detect_header_footer(pages) == set()


def test_header_footer_needs_enough_pages():
    pages = [
        [("머리글", 0.02)],
        [("머리글", 0.02)],
    ]
    # 2페이지뿐이라 min_pages(3) 를 못 넘긴다
    assert detect_header_footer(pages) == set()


def test_header_footer_counts_each_page_once():
    """한 페이지에 같은 텍스트가 두 번 인식돼도 그 페이지는 1회로 센다."""
    pages = [
        [("머리글", 0.02), ("머리글", 0.03)],
        [("다른 것", 0.02)],
        [("또 다른 것", 0.02)],
        [("무관", 0.02)],
    ]
    assert detect_header_footer(pages) == set()


def test_header_footer_without_position():
    """좌표를 모를 때는 use_position=False 로 텍스트 반복만 본다."""
    bodies = ["첫째 줄입니다", "둘째 줄입니다", "셋째 줄입니다", "넷째 줄입니다"]
    pages = [[("머리글", None), (bodies[i], None)] for i in range(4)]
    found = detect_header_footer(pages, use_position=False)
    assert found == {(0, 0), (1, 0), (2, 0), (3, 0)}


def test_digit_normalization_collapses_lines_differing_only_by_number():
    """숫자만 다른 줄은 같은 것으로 묶인다 — 의도된 동작이고 대가가 있다.

    "제3장 사업개요" 와 "제4장 사업개요" 를 같은 머리글로 보려면 필요하다.
    반대로 본문에서 숫자만 다른 줄이 반복으로 오인될 수 있어서, 기본값이
    use_position=True (상·하단 대역만 본다) 인 이유다.
    """
    assert normalize_repeated_text("제3장 사업개요") == normalize_repeated_text("제4장 사업개요")

    pages = [[("본문 " + str(i), None)] for i in range(4)]
    # 좌표를 무시하면 본문까지 반복으로 잡힌다
    assert detect_header_footer(pages, use_position=False) == {(0, 0), (1, 0), (2, 0), (3, 0)}
    # 좌표를 보면 본문 대역이라 잡지 않는다
    positioned = [[("본문 " + str(i), 0.5)] for i in range(4)]
    assert detect_header_footer(positioned) == set()


def test_header_footer_empty_input():
    assert detect_header_footer([]) == set()
