# =============================================================================
# 이 파일의 책임: 추출기가 뱉은 텍스트에서 보이지 않는 제어문자를 걷어낸다.
#
# 왜 필요한가 ① 저장이 실패한다:
#   PostgreSQL 의 text 는 NUL(0x00) 을 담지 못한다. 넣으려 하면
#   `ValueError: A string literal cannot contain NUL (0x00) characters.` 로
#   INSERT 가 실패한다. PDF · OCR 추출은 NUL 을 흘릴 수 있다.
#
#   실제로 겪었다: 공공 SI 문서 86건 중 1건에 NUL 이 59개 들어 있었고,
#   그 하나 때문에 86건 적재 트랜잭션이 **통째로** 실패했다. 사용자가 그런
#   문서를 올리면 추출은 성공했는데 저장에서 죽는다.
#
# 왜 필요한가 ② 원문 대조가 조용히 어긋난다 (2026-09-01 에 추가한 이유):
#   NUL 말고 다른 제어문자는 저장은 되기 때문에 오래 눈에 띄지 않았다. 그런데
#   요약의 근거 인용은 `quote not in chunk.text` 로 **글자 단위 대조**를 한다.
#   조달청 재공고서 1건에 \x01 이 516개 박혀 있었고, 이렇게 생겼다:
#
#       '이계약은「국가를당사자로하는계약에관한법률」 \x01 제5조의2에따른…'
#
#   모델은 사람이 읽는 대로 옮겨 적으므로 \x01 을 빼고 쓴다. 사람 눈에는
#   똑같은 문장인데 대조는 실패한다. 화면에는 «근거 추출 검증 실패» 만 뜨고
#   왜 실패했는지는 보이지 않는다 — 원인이 보이지 않는 문자이기 때문이다.
#
# 다른 파일과의 관계: services/extraction_service.py 의 _extract() 가 추출기
#   결과를 받자마자 이것을 통과시킨다. 추출기가 여럿(pdf · docx · hwpx · image ·
#   ocr)이므로 각각에 넣지 않고 **한 경계에서** 처리한다.
#
# ⚠️ 지우지 않고 **공백으로 바꾼다.** 길이가 바뀌면 안 되기 때문이다.
#   pdf_extractor · image_extractor 는 ExtractedElement.content_start 를 직접
#   설정하는데, 그 값은 content 문자열의 위치를 가리킨다. 제어문자를 제거하면
#   그 뒤의 모든 오프셋이 한 칸씩 밀려 **청크가 원문 어디서 왔는지가 조용히
#   어긋난다.** 같은 길이로 치환하면 오프셋도 char_count 도 그대로 유효하다.
#   제어문자는 어차피 표시되지 않으므로 공백으로 바뀌어도 잃는 것이 없다.
#
# ⚠️ 탭 · 줄바꿈 · 캐리지리턴(\t \n \r)은 **남긴다.** 문단 구조를 나르는
#   진짜 공백문자이고, structure.py 의 문단 판정과 split_document 의 경계
#   탐색이 \n\n 을 본다. 이것까지 공백으로 바꾸면 문서가 한 덩어리가 된다.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import replace

from app.extractors.protocol import ExtractResult

# C0 제어문자 전체 + DEL 에서 \t(09) \n(0a) \r(0d) 만 뺀 것.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# 길이를 유지해야 오프셋이 살아남는다. 반드시 한 글자여야 한다.
REPLACEMENT = " "


def scrub_text(text: str) -> str:
    """제어문자를 같은 길이의 공백으로 바꾼다."""
    return CONTROL.sub(REPLACEMENT, text)


def count_control(text: str) -> int:
    return len(CONTROL.findall(text))


def scrub_result(result: ExtractResult) -> tuple[ExtractResult, int]:
    """추출 결과 전체를 훑어 제어문자를 걷어낸다.

    (정리된 결과, 바꾼 개수) 를 돌려준다. 개수를 함께 주는 이유는 호출한 쪽이
    로그를 남길 수 있게 하기 위해서다 — 조용히 고치면 원본 파일에 문제가 있다는
    사실 자체를 아무도 모르게 된다.

    본문뿐 아니라 검수 페이지의 요소 텍스트도 함께 처리한다. 그쪽은
    OcrElement.original_text / text 로 들어가는데 같은 컬럼 제약을 받는다.
    """
    in_content = count_control(result.content)
    in_elements = sum(
        count_control(element.text)
        for page in result.review_pages
        for element in page.elements
    )

    if in_content == 0 and in_elements == 0:
        # 대부분의 문서가 여기로 빠진다. 멀쩡한 입력에 객체를 다시 만들지 않는다.
        return result, 0

    # ⚠️ 둘을 더하면 안 된다. 요소 텍스트는 보통 본문의 한 조각이라 같은 문자가
    #   양쪽에서 세어져 개수가 부풀려진다(로그가 거짓말을 하게 된다).
    #   그렇다고 본문만 세면, 본문은 깨끗한데 요소만 더러운 경우에 0 을 보고하며
    #   조용히 고치게 된다. 큰 쪽을 취하면 두 경우 모두 실제에 가깝다.
    count = max(in_content, in_elements)

    pages = tuple(
        replace(
            page,
            elements=tuple(
                replace(element, text=scrub_text(element.text))
                for element in page.elements
            ),
        )
        for page in result.review_pages
    )
    # char_count 계열은 그대로 둔다 — 길이가 바뀌지 않았으므로 여전히 맞다.
    return replace(result, content=scrub_text(result.content), review_pages=pages), count
