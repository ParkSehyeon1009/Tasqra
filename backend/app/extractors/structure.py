# =============================================================================
# 이 파일의 책임: OCR·추출 결과의 각 요소가 어떤 종류인지(element_type) 자동으로
#   판정한다. 지금은 두 가지를 맡는다.
#     detect_heading()        조항 번호·항목 번호로 시작하는 제목을 찾는다
#     detect_header_footer()  페이지마다 반복되는 머리글·바닥글을 찾는다
#   판정 결과는 element_type_source="AUTO" 로 저장되고, 사람이 검수 화면에서
#   고치면 "USER_CORRECTED" 가 된다. 즉 이 파일은 "제안"만 하고 정답을 우기지 않는다.
#
# 다른 파일과의 관계: 표는 ocr_extractor._build_table_rows 가 이미
#   TABLE_HEADER / TABLE_ROW 를 붙이므로 여기서 다루지 않는다. 여기서 판정한 값은
#   extraction_service 가 OcrElement(element_type=...) 로 넣는다.
#   청킹(RAG-001-1)이 이 값을 입력으로 쓴다 — HEADING 앞에서 끊고,
#   HEADER_FOOTER 는 청킹에서 버린다.
#
# Spring 비교: 도메인 규칙만 담은 순수 유틸리티다. 스프링에서 @Component 로
#   등록하지 않고 static 메서드만 가진 XxxRules 클래스로 두는 자리와 같다.
#   DB·세션·설정에 의존하지 않으므로 단위테스트가 바로 붙는다.
#
# 왜 보수적으로 짰는가
#   HEADING 은 is_paragraph_start=True 를 강제한다(document_service 참고).
#   잘못 붙으면 본문 한가운데서 단락이 끊겨 청크가 조각난다. 반대로 놓치면
#   사람이 검수 화면에서 한 번 누르면 된다. 그래서 애매하면 TEXT_LINE 으로 남긴다.
#   오탐(false positive)을 미탐보다 비싸게 본다.
# =============================================================================

from __future__ import annotations

import re
from collections import defaultdict
from typing import Sequence

# 제목으로 볼 최대 길이. 이보다 길면 조항 번호로 시작해도 본문 문장으로 본다.
#   "제3조(계약의 목적)"          -> 제목
#   "제3조 이 계약은 ... 한다."   -> 본문. 길이로 걸러진다
HEADING_MAX_CHARS = 60

# 머리글·바닥글을 찾을 페이지 상·하단 비율. 정규화 좌표(0~1) 기준이다.
HEADER_FOOTER_BAND = 0.12

# 반복으로 볼 최소 기준. 페이지 수가 적은 문서에서도 오판하지 않도록 두 조건을 쓴다.
HEADER_FOOTER_MIN_PAGES = 3
HEADER_FOOTER_MIN_RATIO = 0.5


# ── 제목 판정 ────────────────────────────────────────────────────────────────

# 법령·계약서의 조항. "제 3 조" 처럼 띄어 쓰는 경우가 있어 \s* 를 넣는다.
_CLAUSE = re.compile(r"^제\s*\d+\s*[조항목절장편]")

# 번호 항목. "1." "1.2" "1.2.3)" "3)" 을 받는다. 뒤에 내용이 있어야 한다.
_NUMBERED = re.compile(r"^\d+(?:\.\d+)*\s*[.)]\s*\S")

# 한글 항목. "가." "나)" — 가~하 만 받는다. 그 뒤는 관례적으로 쓰이지 않는다.
_HANGUL_ITEM = re.compile(r"^[가-하]\s*[.)]\s*\S")

# 로마자 항목. 전각(Ⅰ~Ⅹ)과 반각(I·V·X 조합) 둘 다.
_ROMAN = re.compile(r"^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]{1,4})\s*[.)]\s*\S")

# 마크다운 제목. corpus 가 .md 인 경우에만 나온다. OCR 결과에는 없다.
_MARKDOWN = re.compile(r"^#{1,6}\s+\S")

# 문장으로 끝나는가.
#   종결 부호가 있거나, 공문서에서 문장을 끝내는 명사형 종결로 끝난다.
#
#   넣은 것 — 다 · 함 · 됨 · 음
#     "~하여야 한다." "~제출함" "~확인됨" "~아래와 같음" 은 전부 본문이다.
#     특히 "~있음" "~없음" "~같음" 이 매우 흔해서 음 을 빼면 오탐이 크게 늘었다.
#
#   뺀 것 — 요 · 임
#     "사업개요" "추진 개요" 가 제목으로 아주 흔하다. 요 를 넣으면 이것을 놓친다.
#     임 은 "책임" "위임" 처럼 제목에도 쓰이고 "~할 것임" 처럼 본문에도 쓰여
#     양쪽 위험이 비슷하다. 판단이 갈리므로 넣지 않고 실측으로 정한다.
_SENTENCE_END = re.compile(r"[.。!?]$|(?:다|함|됨|음)$")

# 번호를 떼고 남은 내용이 이만큼도 안 되면 제목으로 보지 않는다.
# "1." 만 있는 줄(표 안의 순번 등)을 걸러낸다.
_MIN_BODY_CHARS = 2

# 숫자·기호만 있는 줄. 제목이 아니다.
#   실측에서 "5.8%" "9.3%" "38.5%" 가 제목으로 잡혔다. _NUMBERED 가 이것을
#   "번호 5 · 내용 8%" 로 읽기 때문이다. 표·차트의 수치가 이렇게 들어온다.
_NUMERIC_ONLY = re.compile(r"^[\d.,%()\-~\s]+$")

# 줄 끝의 괄호 보충 설명. 문장 종결 부호를 가린다.
#   실측에서 "3. 평소 ... 어느 정도입니까? (보안 관련 ... 기준)" 이 제목으로
#   잡혔다. "?" 로 끝나는데 뒤에 괄호가 붙어 종결 판정이 빗나갔다.
_TRAILING_PAREN = re.compile(r"\s*[(（][^)）]*[)）]\s*$")


def detect_heading(text: str, *, max_chars: int = HEADING_MAX_CHARS) -> bool:
    """이 텍스트가 제목인가.

    받는 것 — 조항(제N조) · 번호 항목(1. 1.2 3)) · 한글 항목(가.) ·
              로마자 항목(Ⅱ.) · 마크다운 제목(##)

    받지 않는 것
      글머리 기호(■ ○ ● ▪)  목록 항목이다. 제목으로 보면 목록마다 단락이 끊긴다
      길이 초과              조항 번호로 시작하는 본문 문장을 걸러낸다
      문장 종결              "~한다." "~제출함" 은 본문이다

    번호가 없는 제목("사업 개요" 같은 것)은 판정하지 못한다. 번호·조항이 붙은
    제목만 찾는다. 그것이 청킹에서 가장 믿을 수 있는 경계이기 때문이다.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > max_chars:
        return False

    # 마크다운 제목은 표기 자체가 제목이므로 아래 검사를 건너뛴다.
    if _MARKDOWN.match(stripped):
        return True

    # 숫자·기호만 있는 줄은 표·차트의 수치다. "5.8%" 같은 것.
    if _NUMERIC_ONLY.match(stripped):
        return False

    # 끝의 괄호 보충 설명을 떼고 문장 종결을 본다.
    # "3. ...입니까? (기준)" 처럼 괄호가 종결 부호를 가리는 경우가 있다.
    without_paren = _TRAILING_PAREN.sub("", stripped)
    if _SENTENCE_END.search(without_paren or stripped):
        return False

    for pattern in (_CLAUSE, _NUMBERED, _HANGUL_ITEM, _ROMAN):
        match = pattern.match(stripped)
        if match:
            # 조항은 그 자체가 표제 역할을 하므로 뒤가 비어도 제목으로 본다.
            if pattern is _CLAUSE:
                return True
            if len(stripped) - match.end() + 1 >= _MIN_BODY_CHARS:
                return True
    return False


# ── 머리글·바닥글 판정 ───────────────────────────────────────────────────────

_DIGITS = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")


def normalize_repeated_text(text: str) -> str:
    """반복 비교용으로 텍스트를 정규화한다.

    쪽번호는 페이지마다 달라진다. "- 3 -" 와 "- 4 -" 를 같은 것으로 봐야 하므로
    숫자를 # 으로 바꾼다. 공백도 하나로 줄인다.

    이 치환은 의도적으로 과감하다. "제3장 사업개요" 와 "제4장 사업개요" 도 같은
    것으로 보는데, 장이 넘어가도 이어지는 머리글을 잡으려면 그래야 한다.

    대가로 본문에서는 숫자만 다른 서로 다른 줄이 같은 것으로 묶인다. 그래서
    use_position=True 로 상·하단 대역만 보는 것이 기본값이다.
    좌표 없이(use_position=False) 쓰면 오탐이 늘어난다.
    """
    collapsed = _SPACES.sub(" ", text).strip()
    return _DIGITS.sub("#", collapsed)


def detect_header_footer(
    pages: Sequence[Sequence[tuple[str, float | None]]],
    *,
    band: float = HEADER_FOOTER_BAND,
    min_pages: int = HEADER_FOOTER_MIN_PAGES,
    min_ratio: float = HEADER_FOOTER_MIN_RATIO,
    use_position: bool = True,
) -> set[tuple[int, int]]:
    """머리글·바닥글인 요소의 (페이지 index, 요소 index) 집합을 돌려준다.

    pages 는 페이지마다 (텍스트, y비율) 목록이다. y비율은 정규화 좌표(0~1)이고
    페이지 위쪽이 0 이다. 좌표를 모르면 None 을 주고 use_position=False 로 부른다.

    판정 — 페이지 상·하단 band 안에 있고, 정규화한 텍스트가 여러 페이지에 반복되면
    머리글·바닥글로 본다. "여러" 의 기준은 min_pages 개 이상 또는 전체 페이지의
    min_ratio 이상 중 더 큰 값이다.

    한 페이지 안에 같은 텍스트가 여러 번 나와도 그 페이지는 1회로 센다.
    같은 줄이 두 번 인식된 경우에 값이 부풀지 않게 한다.

    이 함수는 요소 순서를 바꾸지 않는다. 호출한 쪽이 element_type 만 바꿔 넣는다.
    """
    if not pages:
        return set()

    def in_band(y: float | None) -> bool:
        if not use_position:
            return True
        if y is None:
            return False
        return y <= band or y >= 1.0 - band

    # 정규화 텍스트가 몇 개 페이지에 나오는지 센다.
    page_count: dict[str, int] = defaultdict(int)
    for page in pages:
        seen: set[str] = set()
        for text, y in page:
            if not in_band(y):
                continue
            key = normalize_repeated_text(text)
            if key:
                seen.add(key)
        for key in seen:
            page_count[key] += 1

    threshold = max(min_pages, int(len(pages) * min_ratio + 0.5))
    repeated = {key for key, count in page_count.items() if count >= threshold}
    if not repeated:
        return set()

    found: set[tuple[int, int]] = set()
    for page_index, page in enumerate(pages):
        for element_index, (text, y) in enumerate(page):
            if not in_band(y):
                continue
            if normalize_repeated_text(text) in repeated:
                found.add((page_index, element_index))
    return found
