# =============================================================================
# 이 파일의 책임: 문서 본문을 RAG 검색 단위인 "청크"로 자르는 순수 로직이다(RAG-01).
#   DB · 임베딩 모델 · 네트워크를 전혀 모른다. 입력은 텍스트 조각 목록이고 출력은
#   Chunk 목록이다. 그래서 컨테이너 없이 단독 실행으로 검증할 수 있다.
#   자르는 기준은 두 가지를 함께 쓴다.
#     (1) 구조 경계 — element_type(HEADING · TABLE_ROW …)과 is_paragraph_start
#     (2) 토큰 수 상한 — 임베딩 모델 입력 길이를 넘지 않게
#   구조 경계를 우선하고, 그것만으로 너무 커지면 토큰 상한으로 다시 쪼갠다.
# 다른 파일과의 관계:
#   - extractors/structure.py 의 detect_heading() 을 fallback 판정에 쓴다.
#     ocr_elements.element_type 이 이미 채워져 있으면 그 값을 믿고, 아직
#     TEXT_LINE 뿐인 문서(호출부 연결 전)에서는 여기서 직접 판정한다.
#   - models/document.py 의 OcrElement / ExtractedText 를 이 파일이 직접 import
#     하지는 않는다. 서비스 계층(chunking_service.py)이 ORM -> TextUnit 으로
#     바꿔서 넣어준다. 그래야 이 파일이 DB 없이 테스트된다.
#   - models/chunk.py 의 DocumentChunk 컬럼(text · char_count · token_count ·
#     page_number · content_start · content_end)과 Chunk 필드가 1:1 대응한다.
# Spring 비교: @Service 인데 @Transactional 도 Repository 도 없는 순수 도메인
#   로직 클래스에 해당한다. TokenCounter 를 인자로 받는 것은 생성자 주입 대신
#   메서드 주입(Method Injection)을 쓴 것이고, Protocol 은 Java interface 다.
#   Chunk / TextUnit 은 record(불변 DTO)에 대응한다.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Iterable, Protocol, Sequence

from app.extractors.structure import detect_heading

# --- 청킹 기본값 -------------------------------------------------------------
# 임베딩 모델에 넣는 최대 토큰 수. BGE-M3 는 8192 까지 받지만 우리 정확도 측정을
# max_seq_length=1024 로 했기 때문에 그 안에 들어와야 측정값을 그대로 쓸 수 있다.
# 제목 접두어와 앞문맥(overlap)이 뒤에 더 붙으므로 상한을 1024 보다 넉넉히 낮춘다.
MAX_TOKENS = 480
# 이보다 짧은 청크는 다음 청크와 합친다. "제 3 장" 한 줄만 들어간 청크는 검색에
# 걸려도 쓸모가 없다. 단 문서의 마지막 조각은 합칠 대상이 없어 그대로 남는다.
MIN_TOKENS = 48
# 앞 청크의 끝을 다음 청크 앞에 얼마나 겹쳐 넣을지. 문장이 경계에서 잘렸을 때
# 양쪽 청크가 모두 문맥을 갖게 한다. 0 이면 겹치지 않는다.
OVERLAP_TOKENS = 48

# 검색에서 걸러낼 종류. 머리글·바닥글은 모든 페이지에 같은 문자열이 반복되므로
# 청크에 섞이면 "무슨 질의를 넣어도 걸리는 노이즈"가 된다.
DROP_TYPES = frozenset({"HEADER_FOOTER"})
# 표 관련 종류. 같은 table_id 끼리 붙여 두고, 넘칠 때는 헤더행을 반복해 준다.
TABLE_TYPES = frozenset({"TABLE_ROW", "TABLE_HEADER"})

# 한 문자당 평균 토큰 수의 보수적 추정값. XLM-RoBERTa 계열(BGE-M3) 한국어
# 토크나이저는 대략 1 토큰이 1.3~1.5 자에 해당하지만, 상한을 넘기지 않는 쪽이
# 안전하므로 토큰을 과대추정하도록 크게 잡는다.
# !! 이 값은 실측하지 않았다. embed-test 에서 실제 토크나이저로 재서 고쳐야 한다.
#    과대추정이면 청크가 필요보다 짧아질 뿐 오류는 나지 않는다.
CHARS_PER_TOKEN = 1.2

# 문장 끝. 여기서 자르면 문장이 반토막 나지 않는다. 한국어 종결어미는
# structure.py 의 _SENTENCE_END 와 같은 판단을 쓰되, 자를 "위치"가 필요하므로
# 문자 다음에 공백이 오는 지점을 찾는다.
_SENTENCE_BREAK = re.compile(r"(?<=[.。!?])\s+|(?<=[다함됨음])\s+")
# 문장 경계가 없을 때 두 번째 후보. 최소한 줄바꿈이나 공백에서 자른다.
_SOFT_BREAK = re.compile(r"\n+|\s+")

# "가." "나)" 같은 한글 항목 표지. structure.py 의 _HANGUL_ITEM 과 같은 모양이다.
#
# structure.py 의 detect_heading() 은 이것을 제목으로 판정한다. 조달문서에서
# "가. 제출서류는 아래와 같음" 처럼 실제 제목으로 쓰이는 경우가 많아서 그 판정은
# 맞다. 그런데 청킹에서 이것을 "제목 문맥"으로 쓰면 문제가 생긴다.
#
#   2. 입찰 참가 자격          <- 이것이 진짜 제목이다
#   가. ... 요건을 갖춘 자
#   나. 소프트웨어사업자 신고를 마친 자
#   다. 최근 3년간 유사 용역 실적이 있는 자
#
# 항목마다 제목을 갈아치우면 "2. 입찰 참가 자격" 이 사라지고 검색 결과에
# "나. 소프트웨어사업자 신고를 마친 자" 가 제목으로 뜬다. 무슨 항목인지 알 수
# 없고 목록도 조각난다. 그래서 한글 항목은 "단락 경계"로만 쓰고 제목 문맥은
# 상위 것을 유지한다. structure.py 는 고치지 않는다 (판정 자체는 맞으므로).
_LIST_MARKER = re.compile(r"^[가-하]\s*[.)]\s*\S")


def is_strong_heading(text: str) -> bool:
    """제목 문맥을 갈아치울 만한 제목인가.

    detect_heading() 이 True 인 것 중에서 한글 항목 표지(가. 나. 다.)를 뺀 것이다.
    "제 2 장", "3.2 대금 지급", "Ⅲ. 계약 조건" 은 True 이고
    "가. 국가를 당사자로 하는 …" 은 False 다.

    Spring 비교: detect_heading 이 리포지토리에서 가져온 원시 판정이고, 이 함수는
      그것을 우리 도메인 규칙(청킹)에 맞게 한 겹 걸러낸 것이다.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _LIST_MARKER.match(stripped):
        return False
    return detect_heading(stripped)


class TokenCounter(Protocol):
    """텍스트의 토큰 수를 센다.

    구현체를 갈아끼울 수 있게 Protocol 로 둔다. 기본 구현은 문자 수 기반
    근사(CharRatioTokenCounter)이고, 정확한 값이 필요하면 실제 임베딩 모델의
    토크나이저를 쓰는 구현을 넣는다. 청킹 로직 자체는 어느 쪽인지 모른다.

    Spring 비교: Java interface 하나에 구현체 두 개(근사 · 실제)를 두고
      상황에 따라 주입하는 것과 같다.
    """

    def count(self, text: str) -> int:
        ...


class CharRatioTokenCounter:
    """문자 수를 CHARS_PER_TOKEN 으로 나눠 토큰 수를 추정한다.

    토크나이저 파일을 내려받지 않아도 동작하는 것이 목적이다. 임베딩 라이브러리가
    아직 없는 환경(지금)과 오프라인 환경에서 청킹만 먼저 돌려볼 수 있게 한다.
    """

    def __init__(self, chars_per_token: float = CHARS_PER_TOKEN) -> None:
        if chars_per_token <= 0:
            raise ValueError("chars_per_token 은 0 보다 커야 한다")
        self._ratio = chars_per_token

    def count(self, text: str) -> int:
        if not text:
            return 0
        # 올림한다. 빈 문자열이 아니면 최소 1 토큰이다.
        return max(1, int(len(text) / self._ratio + 0.999))


@dataclass(frozen=True)
class TextUnit:
    """청킹의 입력 한 조각. OCR 요소 한 줄 또는 평문 한 줄에 대응한다.

    ocr_elements 의 컬럼을 그대로 옮겨 담은 것이라 필드 이름이 같다. 서비스
    계층에서 ORM 객체를 이걸로 바꿔 넣기 때문에, 이 파일은 SQLAlchemy 를
    import 하지 않아도 된다.
    """

    text: str
    page_number: int | None = None
    element_type: str = "TEXT_LINE"
    is_paragraph_start: bool = False
    table_id: int | None = None
    table_row: int | None = None
    # extracted_texts.content 안에서 이 조각이 차지하는 구간 [start, end).
    # ocr_elements 와 같은 좌표계다. 모르면 None.
    content_start: int | None = None
    content_end: int | None = None


@dataclass(frozen=True)
class Chunk:
    """청킹 결과 한 조각. models/chunk.py 의 DocumentChunk 로 그대로 옮겨진다."""

    seq: int
    text: str
    char_count: int
    token_count: int
    page_number: int | None = None
    content_start: int | None = None
    content_end: int | None = None
    # 이 청크가 어느 제목 밑에 있었는지. text 앞에 이미 붙어 있지만, 검색 결과
    # 화면에서 "출처: 제3장 > 3.2 …" 처럼 따로 보여주려고 남긴다.
    heading: str | None = None


# =============================================================================
# 1단계: 입력을 TextUnit 목록으로 만든다
# =============================================================================


def units_from_plain_text(
    content: str,
    *,
    page_number: int | None = None,
    detect_structure: bool = True,
) -> list[TextUnit]:
    """평문 한 덩어리를 줄 단위 TextUnit 으로 쪼갠다.

    ocr_elements 가 없는 문서(PDF 텍스트 레이어만 있는 경우)와, element_type 이
    아직 전부 TEXT_LINE 인 문서에서 쓴다. content 안의 문자 위치를 그대로
    content_start / content_end 에 넣으므로 좌표계가 유지된다.

    detect_structure=True 면 structure.py 의 detect_heading() 으로 제목을 찾아
    element_type 을 HEADING 으로 올린다. 머리글·바닥글 판정은 페이지 좌표가
    필요해서 여기서는 못 한다 (detect_header_footer 는 x·y 를 받는다).
    """
    units: list[TextUnit] = []
    cursor = 0
    for raw_line in content.split("\n"):
        start = cursor
        cursor += len(raw_line) + 1  # +1 은 split 으로 사라진 "\n"
        line = raw_line.strip()
        if not line:
            continue
        # strip 으로 앞에서 깎인 만큼 시작 위치를 밀어 준다. 그래야 content 의
        # 실제 문자 위치와 맞는다.
        lead = len(raw_line) - len(raw_line.lstrip())
        unit_start = start + lead
        is_heading = detect_structure and is_strong_heading(line)
        units.append(
            TextUnit(
                text=line,
                page_number=page_number,
                element_type="HEADING" if is_heading else "TEXT_LINE",
                # 제목은 항상 새 단락의 시작이다.
                is_paragraph_start=is_heading,
                content_start=unit_start,
                content_end=unit_start + len(line),
            )
        )
    return units


def units_from_elements(elements: Iterable[TextUnit]) -> list[TextUnit]:
    """ocr_elements 에서 온 TextUnit 을 청킹에 쓸 수 있게 보정한다.

    재정님 호출부가 아직 연결되지 않아 element_type 이 전부 TEXT_LINE ·
    is_paragraph_start 가 전부 False 인 상태에서도 동작해야 한다. 그래서
    "구조 정보가 하나도 없어 보이면" detect_heading() 으로 직접 채운다.
    나중에 호출부가 붙어 값이 들어오면 그 값을 그대로 존중한다.
    """
    items = list(elements)
    if not items:
        return []

    # 구조 정보가 실제로 들어있는지 본다. 하나라도 TEXT_LINE 이 아니거나
    # 단락 시작 표시가 있으면 이미 채워진 것으로 보고 건드리지 않는다.
    has_structure = any(
        u.element_type != "TEXT_LINE" or u.is_paragraph_start for u in items
    )
    if has_structure:
        return items

    # 전부 기본값이다 -> 우리가 판정한다. 한글 항목(가. 나. 다.)은 제목으로 올리지
    # 않되 단락 시작으로는 표시한다. 목록이 한 청크에 모여 있게 하려는 것이다.
    out: list[TextUnit] = []
    for u in items:
        strong = is_strong_heading(u.text)
        listed = bool(_LIST_MARKER.match(u.text.strip()))
        out.append(
            replace(
                u,
                element_type="HEADING" if strong else u.element_type,
                is_paragraph_start=strong or listed,
            )
        )
    return out


# =============================================================================
# 2단계: TextUnit 목록을 Chunk 목록으로 자른다 — 여기가 진짜 로직이다
# =============================================================================


def chunk_units(
    units: Sequence[TextUnit],
    *,
    counter: TokenCounter | None = None,
    max_tokens: int = MAX_TOKENS,
    min_tokens: int = MIN_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    keep_heading_prefix: bool = True,
) -> list[Chunk]:
    """구조 경계와 토큰 상한으로 청크를 만든다.

    규칙은 다음 순서로 적용한다.
      1. HEADER_FOOTER 는 버린다 (모든 페이지에 반복되는 노이즈).
      2. HEADING 을 만나면 청크를 끊고, 그 제목을 이후 청크의 접두어로 유지한다.
         제목이 없으면 "3.2 대금 지급" 밑의 본문만 검색되어 무슨 항목인지 모른다.
      3. is_paragraph_start=True 에서 끊을 수 있으면 끊는다.
      4. 같은 table_id 는 붙여 둔다. 넘치면 쪼개고 TABLE_HEADER 를 각 조각에
         반복해 넣는다. 표 행만 떨어져 나가면 열 이름을 잃는다.
      5. 위로도 상한을 넘으면 문장 경계 -> 공백 -> 강제 로 잘라낸다.
      6. min_tokens 미만 청크는 다음 청크에 붙인다.

    반환하는 Chunk 의 seq 는 0 부터 1 씩 증가한다 (uq_document_chunk_seq).
    """
    counter = counter or CharRatioTokenCounter()
    if max_tokens <= 0:
        raise ValueError("max_tokens 는 0 보다 커야 한다")
    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens 는 0 이상 max_tokens 미만이어야 한다")

    kept = [u for u in units if u.element_type not in DROP_TYPES and u.text.strip()]
    if not kept:
        return []

    groups = _group_units(kept)

    raw: list[_Draft] = []
    for group in groups:
        raw.extend(
            _chunk_group(
                group,
                counter=counter,
                max_tokens=max_tokens,
                keep_heading_prefix=keep_heading_prefix,
            )
        )

    merged = _merge_short(raw, counter=counter, min_tokens=min_tokens, max_tokens=max_tokens)
    with_overlap = _apply_overlap(
        merged, counter=counter, overlap_tokens=overlap_tokens, max_tokens=max_tokens
    )
    return _finalize(with_overlap, counter=counter)


# --- 이하 내부 구현 ----------------------------------------------------------


@dataclass
class _Draft:
    """확정 전 청크. seq 를 아직 안 붙였고 본문도 더 붙을 수 있다."""

    text: str
    page_number: int | None
    content_start: int | None
    content_end: int | None
    heading: str | None
    # 제목 접두어처럼 본문 앞에 덧붙은 부분. 겹침(overlap)을 계산할 때
    # 본문만 대상으로 하려고 따로 들고 있는다.
    prefix: str = ""


@dataclass
class _Group:
    """한 번에 처리할 단위 묶음. 제목 하나와 그 밑의 본문 또는 표 하나다."""

    units: list[TextUnit]
    heading: str | None
    table_id: int | None


def _group_units(units: Sequence[TextUnit]) -> list[_Group]:
    """제목 · 단락 시작 · 표 경계로 단위를 묶는다."""
    groups: list[_Group] = []
    current: list[TextUnit] = []
    heading: str | None = None
    table_id: int | None = None

    def flush() -> None:
        nonlocal current, table_id
        if current:
            groups.append(_Group(units=current, heading=heading, table_id=table_id))
            current = []
            table_id = None

    for unit in units:
        stripped = unit.text.strip()
        listed = bool(_LIST_MARKER.match(stripped))

        # 제목은 경계다. 단 한글 항목(가. 나. 다.)은 제외한다 — DB 의 element_type 이
        # HEADING 이어도 제목 문맥을 갈아치우지 않고 본문처럼 다룬다. 이유는
        # _LIST_MARKER 주석에 적었다.
        if unit.element_type == "HEADING" and not listed:
            flush()
            heading = stripped
            # 제목 자체도 본문에 들어가야 검색된다. 다음 묶음의 첫 줄로 둔다.
            current = [unit]
            continue

        in_table = unit.element_type in TABLE_TYPES
        if in_table:
            if table_id is not None and unit.table_id != table_id:
                # 다른 표로 넘어갔다.
                flush()
            elif table_id is None and current and not _all_table(current):
                # 본문에서 표로 넘어갔다.
                flush()
            table_id = unit.table_id
        else:
            if table_id is not None:
                # 표에서 본문으로 돌아왔다.
                flush()
            # 한글 항목은 단락 시작 표시가 있어도 끊지 않는다. 같은 목록을 한
            # 청크에 모아 두는 편이 검색에 낫다. 상한을 넘으면 _chunk_group 이 쪼갠다.
            if unit.is_paragraph_start and current and not listed:
                flush()

        current.append(unit)

    flush()
    return groups


def _all_table(units: Sequence[TextUnit]) -> bool:
    return bool(units) and all(u.element_type in TABLE_TYPES for u in units)


def _chunk_group(
    group: _Group,
    *,
    counter: TokenCounter,
    max_tokens: int,
    keep_heading_prefix: bool,
) -> list[_Draft]:
    """묶음 하나를 토큰 상한에 맞게 자른다."""
    # 제목 접두어. 두 번째 조각부터 붙인다 (첫 조각에는 제목 줄 자체가 이미 있다).
    prefix = ""
    if keep_heading_prefix and group.heading:
        prefix = group.heading + "\n"

    # 표라면 헤더행을 뽑아 각 조각에 반복해 넣는다.
    table_header = ""
    if group.table_id is not None:
        header_units = [u for u in group.units if u.element_type == "TABLE_HEADER"]
        if header_units:
            table_header = "\n".join(u.text.strip() for u in header_units)

    # 두 번째 조각부터는 제목 접두어와 표 헤더행이 함께 앞에 붙는다. 그 둘의
    # 토큰을 예산에서 미리 빼지 않으면 조각이 상한을 넘는다. 첫 조각은 접두어가
    # 없어 예산이 조금 남지만, 어떤 조각도 상한을 넘지 않는 쪽을 택한다.
    prefix_tokens = counter.count(prefix) if prefix else 0
    header_tokens = counter.count(table_header + "\n") if table_header else 0
    budget = max_tokens - prefix_tokens - header_tokens
    if budget <= 0:
        # 접두어가 상한을 다 먹는 비정상 상황. 제목 접두어를 먼저 포기한다.
        prefix = ""
        prefix_tokens = 0
        budget = max_tokens - header_tokens
    if budget <= 0:
        # 표 헤더행조차 상한을 넘는다. 반복을 포기한다.
        table_header = ""
        header_tokens = 0
        budget = max_tokens

    drafts: list[_Draft] = []
    buf: list[TextUnit] = []
    buf_tokens = 0

    def emit(first: bool) -> None:
        nonlocal buf, buf_tokens
        if not buf:
            return
        body = "\n".join(u.text.strip() for u in buf)
        head = "" if first else prefix
        if table_header and not first and table_header not in body:
            head = head + table_header + "\n"
        drafts.append(
            _Draft(
                text=head + body,
                page_number=_first_page(buf),
                content_start=_span_start(buf),
                content_end=_span_end(buf),
                heading=group.heading,
                prefix=head,
            )
        )
        buf = []
        buf_tokens = 0

    for unit in group.units:
        text = unit.text.strip()
        tokens = counter.count(text)

        if tokens > budget:
            # 한 줄 자체가 상한을 넘는다 (긴 표 행, 줄바꿈 없는 문단).
            emit(first=not drafts)
            for piece in _split_long_text(text, counter=counter, limit=budget):
                first = not drafts
                head = "" if first else prefix
                if table_header and not first:
                    head = head + table_header + "\n"
                drafts.append(
                    _Draft(
                        text=head + piece,
                        page_number=unit.page_number,
                        # 쪼갠 조각의 정확한 본문 위치는 알 수 없다. 원 줄의
                        # 구간을 그대로 두면 겹쳐서 틀린 하이라이트가 되므로 버린다.
                        content_start=None,
                        content_end=None,
                        heading=group.heading,
                        prefix=head,
                    )
                )
            continue

        if buf and buf_tokens + tokens > budget:
            emit(first=not drafts)

        buf.append(unit)
        buf_tokens += tokens

    emit(first=not drafts)
    return drafts


def _split_long_text(text: str, *, counter: TokenCounter, limit: int) -> list[str]:
    """상한을 넘는 한 덩어리를 문장 -> 공백 -> 강제 순으로 자른다."""
    if counter.count(text) <= limit:
        return [text]

    parts = [p for p in _SENTENCE_BREAK.split(text) if p and p.strip()]
    if len(parts) <= 1:
        parts = [p for p in _SOFT_BREAK.split(text) if p and p.strip()]

    out: list[str] = []
    buf: list[str] = []
    buf_tokens = 0
    for part in parts:
        tokens = counter.count(part)
        if tokens > limit:
            # 공백조차 없는 초장문. 문자 수로 강제 절단한다.
            if buf:
                out.append(" ".join(buf))
                buf, buf_tokens = [], 0
            out.extend(_hard_split(part, counter=counter, limit=limit))
            continue
        if buf and buf_tokens + tokens > limit:
            out.append(" ".join(buf))
            buf, buf_tokens = [], 0
        buf.append(part)
        buf_tokens += tokens
    if buf:
        out.append(" ".join(buf))
    return out or [text]


def _hard_split(text: str, *, counter: TokenCounter, limit: int) -> list[str]:
    """문자 수로 자른다. 마지막 수단이다."""
    # 토큰 상한을 문자 수로 되돌린다. counter 가 근사든 실제든 이분 없이
    # 단순 비례로 잡고, 넘치면 조금 줄여 다시 시도한다.
    approx = max(1, int(limit * CHARS_PER_TOKEN))
    out: list[str] = []
    i = 0
    while i < len(text):
        size = approx
        piece = text[i : i + size]
        while size > 1 and counter.count(piece) > limit:
            size = int(size * 0.9) or 1
            piece = text[i : i + size]
        out.append(piece)
        i += len(piece)
    return out


def _merge_short(
    drafts: Sequence[_Draft],
    *,
    counter: TokenCounter,
    min_tokens: int,
    max_tokens: int,
) -> list[_Draft]:
    """너무 짧은 청크를 뒤 청크에 붙인다.

    제목 한 줄만 든 청크가 생기는 것을 막는 것이 주 목적이다. 뒤에 붙일 게
    없으면(마지막) 그대로 남긴다 — 짧아도 버리지는 않는다. 문서 끝의 짧은
    문장이 검색에서 사라지면 안 된다.
    """
    out: list[_Draft] = []
    pending: _Draft | None = None

    for draft in drafts:
        if pending is not None:
            joined = pending.text + "\n" + draft.text
            if counter.count(joined) <= max_tokens:
                draft = _Draft(
                    text=joined,
                    page_number=pending.page_number or draft.page_number,
                    content_start=pending.content_start
                    if pending.content_start is not None
                    else draft.content_start,
                    content_end=draft.content_end
                    if draft.content_end is not None
                    else pending.content_end,
                    heading=pending.heading or draft.heading,
                    prefix=pending.prefix,
                )
            else:
                out.append(pending)
            pending = None

        if counter.count(draft.text) < min_tokens:
            pending = draft
            continue
        out.append(draft)

    if pending is not None:
        if out and counter.count(out[-1].text + "\n" + pending.text) <= max_tokens:
            last = out[-1]
            out[-1] = _Draft(
                text=last.text + "\n" + pending.text,
                page_number=last.page_number,
                content_start=last.content_start,
                content_end=pending.content_end
                if pending.content_end is not None
                else last.content_end,
                heading=last.heading,
                prefix=last.prefix,
            )
        else:
            out.append(pending)
    return out


def _apply_overlap(
    drafts: Sequence[_Draft],
    *,
    counter: TokenCounter,
    overlap_tokens: int,
    max_tokens: int,
) -> list[_Draft]:
    """앞 청크의 끝부분을 다음 청크 앞에 겹쳐 넣는다.

    content_start 는 건드리지 않는다. 겹친 부분은 앞 청크의 본문이므로,
    이 청크의 구간을 앞으로 늘리면 두 청크의 구간이 겹쳐 하이라이트가
    이상해진다. 검색 정확도를 위한 것이고 위치 기록용이 아니다.
    """
    if overlap_tokens <= 0 or len(drafts) < 2:
        return list(drafts)

    out = [drafts[0]]
    for prev, cur in zip(drafts, drafts[1:]):
        tail = _tail_by_tokens(prev.text, counter=counter, tokens=overlap_tokens)
        if not tail:
            out.append(cur)
            continue

        # 겹침은 제목 "뒤"에 넣는다. 앞에 넣으면 제목이 청크 중간으로 밀려난다.
        # BGE-M3 는 CLS 풀링이라 앞쪽 토큰이 주제 신호로 더 크게 작용하므로 제목은
        # 반드시 맨 앞에 있어야 한다. 검색 결과 스니펫의 첫 줄이 이전 청크
        # 내용이 되는 것도 막는다.
        #
        # 제목이 앞에 오는 경로가 두 가지다.
        #   (1) 접두어(prefix) — 묶음의 두 번째 조각부터. 제목 + 표 헤더행.
        #   (2) 본문 첫 줄 — 묶음의 첫 조각. 제목 줄 자체가 본문에 들어 있다.
        # (2) 를 빠뜨리면 청크 하나로 끝나는 묶음에서 겹침이 제목 앞에 붙는다.
        lead, body = "", cur.text
        if cur.prefix and cur.text.startswith(cur.prefix):
            lead, body = cur.prefix, cur.text[len(cur.prefix) :]
        elif cur.heading:
            first_line, sep, rest = cur.text.partition("\n")
            if first_line.strip() == cur.heading.strip():
                lead, body = first_line + sep, rest
        merged = lead + tail + "\n" + body
        if counter.count(merged) > max_tokens:
            out.append(cur)
            continue

        out.append(
            _Draft(
                text=merged,
                page_number=cur.page_number,
                # content 구간은 이 청크가 원래 담당한 범위 그대로 둔다. 겹친
                # 부분은 앞 청크의 본문이라 여기 포함하면 두 청크의 구간이 겹쳐
                # 하이라이트가 어긋난다. 그래서 char_count 와 구간 길이는 다르다.
                content_start=cur.content_start,
                content_end=cur.content_end,
                heading=cur.heading,
                prefix=cur.prefix,
            )
        )
    return out


def _tail_by_tokens(text: str, *, counter: TokenCounter, tokens: int) -> str:
    """텍스트의 끝에서 대략 tokens 만큼을 문장 경계로 떼어 온다."""
    parts = [p for p in _SENTENCE_BREAK.split(text) if p and p.strip()]
    if not parts:
        return ""
    picked: list[str] = []
    total = 0
    for part in reversed(parts):
        count = counter.count(part)
        if picked and total + count > tokens:
            break
        picked.insert(0, part)
        total += count
        if total >= tokens:
            break
    tail = " ".join(picked)
    return tail if tail != text.strip() else ""


def _finalize(drafts: Sequence[_Draft], *, counter: TokenCounter) -> list[Chunk]:
    chunks: list[Chunk] = []
    for seq, draft in enumerate(drafts):
        text = draft.text.strip()
        if not text:
            continue
        chunks.append(
            Chunk(
                seq=len(chunks),
                text=text,
                char_count=len(text),
                token_count=counter.count(text),
                page_number=draft.page_number,
                content_start=draft.content_start,
                content_end=draft.content_end,
                heading=draft.heading,
            )
        )
    return chunks


def _first_page(units: Sequence[TextUnit]) -> int | None:
    for u in units:
        if u.page_number is not None:
            return u.page_number
    return None


def _span_start(units: Sequence[TextUnit]) -> int | None:
    values = [u.content_start for u in units if u.content_start is not None]
    return min(values) if values else None


def _span_end(units: Sequence[TextUnit]) -> int | None:
    values = [u.content_end for u in units if u.content_end is not None]
    return max(values) if values else None
