"""추출 결과에서 NUL(0x00) 을 걷어내는 동작을 확인한다.

PostgreSQL 의 text 는 NUL 을 담지 못한다. 하나만 섞여도 저장이 통째로 실패한다.

핵심은 "지우는 것" 이 아니라 "같은 길이로 바꾸는 것" 이다. pdf_extractor 와
image_extractor 는 content_start 를 직접 설정하는데, 길이가 바뀌면 그 뒤의
모든 오프셋이 밀려 청크가 원문 어디서 왔는지가 조용히 어긋난다.
"""

from app.extractors.protocol import ExtractedElement, ExtractedPage, ExtractResult
from app.extractors.sanitize import scrub_result, scrub_text


def _element(text: str, start: int) -> ExtractedElement:
    return ExtractedElement(
        x=0.0, y=0.0, width=1.0, height=1.0, text=text,
        content_start=start, content_end=start + len(text),
    )


def _result(content: str, elements: list[ExtractedElement] | None = None) -> ExtractResult:
    pages = ()
    if elements is not None:
        pages = (
            ExtractedPage(
                page_number=1, width=100, height=100, image_bytes=b"",
                elements=tuple(elements),
            ),
        )
    return ExtractResult(
        content=content, page_count=1, char_count=len(content),
        text_char_count=len(content), ocr_char_count=0,
        extract_method="text", review_pages=pages,
    )


def test_scrub_text_은_길이를_유지한다():
    before = "앞\x00뒤"
    after = scrub_text(before)
    assert "\x00" not in after
    assert len(after) == len(before)


def test_nul_이_없으면_원본을_그대로_돌려준다():
    result = _result("깨끗한 본문")
    cleaned, count = scrub_result(result)
    assert count == 0
    # 멀쩡한 입력에 객체를 다시 만들지 않는다.
    assert cleaned is result


def test_본문의_nul_을_바꾸고_개수를_돌려준다():
    result = _result("계약\x00기간\x00은 5개월")
    cleaned, count = scrub_result(result)
    assert count == 2
    assert "\x00" not in cleaned.content
    assert cleaned.content == "계약 기간 은 5개월"


def test_길이가_바뀌지_않아_char_count_가_그대로_맞는다():
    result = _result("계약\x00기간")
    cleaned, _ = scrub_result(result)
    assert len(cleaned.content) == cleaned.char_count


def test_요소_오프셋이_보존된다():
    """이 수정의 핵심. NUL 을 제거했다면 이 검사가 깨진다."""
    content = "머리말 계약\x00기간 꼬리말"
    start = content.index("계약")
    result = _result(content, [_element("계약\x00기간", start)])

    cleaned, count = scrub_result(result)
    assert count == 1

    element = cleaned.review_pages[0].elements[0]
    assert "\x00" not in element.text
    # 오프셋이 그대로이고, 그 자리에서 잘라내면 요소 본문과 같아야 한다.
    assert element.content_start == start
    assert cleaned.content[element.content_start:element.content_end] == element.text


def test_요소에만_nul_이_있어도_잡는다():
    content = "본문은 깨끗하다"
    result = _result(content, [_element("요소\x00텍스트", 0)])
    cleaned, count = scrub_result(result)
    assert count == 1
    assert "\x00" not in cleaned.review_pages[0].elements[0].text
