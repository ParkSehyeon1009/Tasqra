# =============================================================================
# 이 파일의 책임: services/chunking.py 의 청킹 규칙을 검증한다. 구조 경계(제목 ·
#   단락 · 표)와 토큰 상한이 실제로 지켜지는지, 그리고 DocumentChunk 제약
#   조건(seq 연속 · char_count · token_count · content 구간)을 만족하는 값이
#   나오는지 본다.
# 다른 파일과의 관계: app/services/chunking.py 만 대상으로 한다. DB · 임베딩 ·
#   네트워크를 쓰지 않으므로 컨테이너 없이 python 만으로 돌아간다.
# Spring 비교: 순수 도메인 로직에 대한 단위 테스트다. @SpringBootTest 없이
#   new 로 객체를 만들어 검증하는 것과 같다.
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chunking import (  # noqa: E402
    CharRatioTokenCounter,
    Chunk,
    TextUnit,
    chunk_units,
    units_from_elements,
    units_from_plain_text,
)

# 통과한 검사 이름. 단독 실행할 때 몇 개를 봤는지 세는 용도다.
# pytest 로 돌릴 때는 쓰이지 않는다.
PASS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    """검사 하나. 실패하면 AssertionError 를 던진다.

    assert 로 던지는 것이 중요하다. 실패를 리스트에 모으기만 하면 pytest 가
    이 파일을 수집해도 "통과"로 보고한다 — 로직이 깨져도 초록색이 된다.
    아래 __main__ 블록이 테스트 함수 단위로 예외를 잡아 요약을 만든다.
    """
    assert condition, f"{name}{' — ' + detail if detail else ''}"
    PASS.append(name)


def invariants(chunks: list[Chunk], *, max_tokens: int, label: str) -> None:
    """모든 청크가 DB 제약을 만족하는지 확인한다."""
    check(f"[{label}] seq 는 0 부터 연속", [c.seq for c in chunks] == list(range(len(chunks))))
    check(f"[{label}] text 가 비지 않음", all(c.text.strip() for c in chunks))
    check(f"[{label}] char_count 일치", all(c.char_count == len(c.text) for c in chunks))
    check(f"[{label}] token_count >= 0", all(c.token_count >= 0 for c in chunks))
    over = [c.seq for c in chunks if c.token_count > max_tokens]
    check(f"[{label}] 토큰 상한 준수", not over, f"초과 seq={over}")
    bad = [
        c.seq
        for c in chunks
        if c.content_start is not None
        and c.content_end is not None
        and c.content_end < c.content_start
    ]
    check(f"[{label}] content_end >= content_start", not bad, f"위반 seq={bad}")
    half = [
        c.seq
        for c in chunks
        if (c.content_start is None) != (c.content_end is None)
    ]
    check(f"[{label}] content 구간은 둘 다 있거나 둘 다 없음", not half, f"위반 seq={half}")


# =============================================================================
# 1. 평문 — 제목이 경계가 되는지
# =============================================================================

NOTICE = """제 1 장 총칙

1. 목적
이 공고는 정보시스템 구축 용역의 입찰 참가 자격과 절차를 정한다. 입찰에
참가하려는 자는 다음 각 호의 요건을 모두 갖추어야 한다.

2. 입찰 참가 자격
가. 국가를 당사자로 하는 계약에 관한 법률 시행령 제12조의 요건을 갖춘 자
나. 소프트웨어사업자 신고를 마친 자
다. 최근 3년간 유사 용역 실적이 있는 자

제 2 장 계약 및 대금

3. 계약 기간
계약 체결일부터 12개월로 한다. 다만 발주기관이 필요하다고 인정하는 경우
계약 기간을 연장할 수 있다.

4. 대금 지급
준공 검사 완료 후 30일 이내에 지급한다. 선금은 계약 금액의 70퍼센트
범위에서 지급할 수 있으며, 이 경우 선금 지급 보증서를 제출하여야 한다.
"""


def test_plain_text() -> None:
    units = units_from_plain_text(NOTICE, page_number=1)
    headings = [u.text for u in units if u.element_type == "HEADING"]
    check("제목을 찾았다", len(headings) >= 4, f"찾은 제목={headings}")
    check("제 1 장 을 제목으로 봤다", any("제 1 장" in h for h in headings))
    check("4. 대금 지급 을 제목으로 봤다", any("대금 지급" in h for h in headings))
    check(
        "본문 문장은 제목이 아니다",
        not any("30일 이내에 지급한다" in h for h in headings),
    )

    # content 구간이 원문과 실제로 일치하는지 — 이게 틀리면 하이라이트가 어긋난다
    mismatched = [
        u.text
        for u in units
        if NOTICE[u.content_start : u.content_end] != u.text
    ]
    check("content 구간이 원문과 일치", not mismatched, f"불일치={mismatched[:3]}")

    chunks = chunk_units(units, max_tokens=120, min_tokens=20, overlap_tokens=0)
    invariants(chunks, max_tokens=120, label="평문")
    check("청크가 여러 개 나왔다", len(chunks) >= 3, f"개수={len(chunks)}")
    check(
        "제목이 청크에 남아 있다",
        any("제 1 장" in c.text for c in chunks),
    )
    check(
        "heading 필드가 채워졌다",
        any(c.heading for c in chunks),
        f"heading={[c.heading for c in chunks]}",
    )
    # pytest 는 테스트 함수가 값을 돌려주면 경고를 낸다(향후 에러). 그래서
    # 반환하지 않고, 아래 __main__ 에서 필요하면 다시 만든다.


# =============================================================================
# 2. 머리글·바닥글은 버린다
# =============================================================================


def test_drop_header_footer() -> None:
    units = [
        TextUnit(text="한국지역난방공사", element_type="HEADER_FOOTER", page_number=1),
        TextUnit(text="입찰 참가 자격은 다음과 같다.", page_number=1, is_paragraph_start=True),
        TextUnit(text="- 3 -", element_type="HEADER_FOOTER", page_number=1),
    ]
    chunks = chunk_units(units, max_tokens=200, min_tokens=1, overlap_tokens=0)
    joined = "\n".join(c.text for c in chunks)
    check("머리글이 빠졌다", "한국지역난방공사" not in joined)
    check("바닥글이 빠졌다", "- 3 -" not in joined)
    check("본문은 남았다", "입찰 참가 자격" in joined)


# =============================================================================
# 3. 표 — 같은 table_id 는 붙고, 쪼개지면 헤더가 반복된다
# =============================================================================


def test_table() -> None:
    units = [TextUnit(text="5. 산출 내역", element_type="HEADING", page_number=2)]
    units.append(
        TextUnit(
            text="항목 | 단위 | 수량 | 단가 | 금액",
            element_type="TABLE_HEADER",
            table_id=1,
            table_row=0,
            page_number=2,
        )
    )
    for i in range(1, 41):
        units.append(
            TextUnit(
                text=f"응용소프트웨어 개발 {i} | 인월 | {i} | 5,600,000 | {i * 5_600_000:,}",
                element_type="TABLE_ROW",
                table_id=1,
                table_row=i,
                page_number=2,
            )
        )

    chunks = chunk_units(units, max_tokens=150, min_tokens=10, overlap_tokens=0)
    invariants(chunks, max_tokens=150, label="표")
    check("표가 여러 청크로 쪼개졌다", len(chunks) >= 2, f"개수={len(chunks)}")
    with_header = [c for c in chunks if "항목 | 단위 | 수량" in c.text]
    check(
        "쪼개진 모든 표 청크에 헤더행이 있다",
        len(with_header) == len(chunks),
        f"{len(with_header)}/{len(chunks)} 에만 있다",
    )
    check(
        "표 행이 반토막 나지 않았다",
        all(c.text.count("|") % 4 == 0 for c in chunks if "|" in c.text)
        or all("응용소프트웨어" in c.text for c in chunks if "|" in c.text),
    )


def test_two_tables_separate() -> None:
    units = [
        TextUnit(text="구분 | 금액", element_type="TABLE_HEADER", table_id=1, table_row=0),
        TextUnit(text="직접비 | 100", element_type="TABLE_ROW", table_id=1, table_row=1),
        TextUnit(text="연도 | 실적", element_type="TABLE_HEADER", table_id=2, table_row=0),
        TextUnit(text="2025 | 3건", element_type="TABLE_ROW", table_id=2, table_row=1),
    ]
    chunks = chunk_units(units, max_tokens=500, min_tokens=1, overlap_tokens=0)
    check("서로 다른 표는 다른 청크로 갔다", len(chunks) == 2, f"개수={len(chunks)}")
    if len(chunks) == 2:
        check("첫 표에 둘째 표가 섞이지 않았다", "연도" not in chunks[0].text)


# =============================================================================
# 4. 상한을 넘는 한 줄
# =============================================================================


def test_long_line() -> None:
    long_line = (
        "계약상대자는 계약 이행 중 발생한 모든 안전사고에 대하여 책임을 진다. " * 40
    )
    units = [TextUnit(text=long_line, page_number=5)]
    chunks = chunk_units(units, max_tokens=100, min_tokens=1, overlap_tokens=0)
    invariants(chunks, max_tokens=100, label="장문")
    check("장문이 쪼개졌다", len(chunks) > 1, f"개수={len(chunks)}")
    check(
        "쪼갠 조각은 content 구간을 버렸다",
        all(c.content_start is None for c in chunks),
    )
    # 글자가 사라지지 않았는지 — 공백 차이는 무시하고 비교
    restored = "".join(c.text for c in chunks).replace(" ", "").replace("\n", "")
    original = long_line.replace(" ", "")
    check(
        "쪼개는 과정에서 글자가 사라지지 않았다",
        restored == original,
        f"원본 {len(original)}자 -> 복원 {len(restored)}자",
    )


def test_no_space_long_line() -> None:
    units = [TextUnit(text="가" * 2000)]
    chunks = chunk_units(units, max_tokens=50, min_tokens=1, overlap_tokens=0)
    invariants(chunks, max_tokens=50, label="공백없는장문")
    check("공백 없는 장문도 쪼개진다", len(chunks) > 1, f"개수={len(chunks)}")
    check(
        "공백 없는 장문에서 글자가 사라지지 않았다",
        "".join(c.text for c in chunks) == "가" * 2000,
    )


# =============================================================================
# 5. 짧은 청크 병합
# =============================================================================


def test_merge_short() -> None:
    units = [
        TextUnit(text="제 3 장 하자보수", element_type="HEADING"),
        TextUnit(
            text="하자담보책임기간은 준공 검사 완료일부터 1년으로 한다. "
            "다만 발주기관이 따로 정한 경우에는 그에 따른다.",
            is_paragraph_start=True,
        ),
    ]
    chunks = chunk_units(units, max_tokens=500, min_tokens=40, overlap_tokens=0)
    check("제목만 든 청크가 남지 않았다", len(chunks) == 1, f"개수={len(chunks)}")
    if chunks:
        check("병합된 청크에 제목과 본문이 함께 있다", "제 3 장" in chunks[0].text and "하자담보" in chunks[0].text)


def test_last_short_chunk_kept() -> None:
    units = [
        TextUnit(text="본문이 충분히 길어서 그 자체로 하나의 청크가 되는 문장이다. " * 5),
        TextUnit(text="끝.", is_paragraph_start=True),
    ]
    chunks = chunk_units(units, max_tokens=500, min_tokens=40, overlap_tokens=0)
    joined = "\n".join(c.text for c in chunks)
    check("문서 끝의 짧은 조각이 버려지지 않았다", "끝." in joined)


# =============================================================================
# 6. 겹침(overlap)
# =============================================================================


def test_overlap() -> None:
    units = units_from_plain_text(NOTICE, page_number=1)
    no_ov = chunk_units(units, max_tokens=120, min_tokens=20, overlap_tokens=0)
    with_ov = chunk_units(units, max_tokens=120, min_tokens=20, overlap_tokens=30)
    invariants(with_ov, max_tokens=120, label="겹침")
    check(
        "겹침을 넣으면 글자 수 총합이 늘어난다",
        sum(c.char_count for c in with_ov) > sum(c.char_count for c in no_ov),
    )
    check(
        "겹침이 content 구간을 앞으로 늘리지 않았다",
        all(
            a.content_start == b.content_start
            for a, b in zip(no_ov, with_ov)
            if a.content_start is not None and b.content_start is not None
        ),
    )
    # BGE-M3 는 CLS 풀링이라 앞쪽 토큰이 주제 신호로 크게 작용한다. 겹침 때문에
    # 제목이 뒤로 밀리면 검색 품질이 떨어지고 결과 스니펫 첫 줄도 엉뚱해진다.
    misplaced = [c.seq for c in with_ov if c.heading and not c.text.startswith(c.heading)]
    check(
        "겹침이 있어도 제목이 청크 맨 앞에 있다",
        not misplaced,
        f"제목이 앞에 없는 seq={misplaced}",
    )


# =============================================================================
# 7. element_type 이 아직 전부 TEXT_LINE 인 문서 (재정님 호출부 연결 전)
# =============================================================================


def test_fallback_when_no_structure() -> None:
    raw = [
        TextUnit(text="제 1 장 총칙", page_number=1),
        TextUnit(text="이 공고는 입찰 절차를 정한다.", page_number=1),
        TextUnit(text="2. 입찰 참가 자격", page_number=1),
        TextUnit(text="소프트웨어사업자 신고를 마친 자로 한다.", page_number=1),
    ]
    fixed = units_from_elements(raw)
    headings = [u.text for u in fixed if u.element_type == "HEADING"]
    check(
        "구조 정보가 없으면 직접 제목을 판정한다",
        len(headings) == 2,
        f"찾은 제목={headings}",
    )
    check("판정한 제목은 단락 시작이 된다", all(u.is_paragraph_start for u in fixed if u.element_type == "HEADING"))


def test_respect_existing_structure() -> None:
    raw = [
        # 이미 사람이 손댄 문서. 제 1 장 을 일부러 본문으로 표시해 뒀다.
        TextUnit(text="제 1 장 총칙", page_number=1, element_type="TEXT_LINE"),
        TextUnit(text="이 공고는", page_number=1, element_type="HEADING"),
    ]
    fixed = units_from_elements(raw)
    check(
        "이미 채워진 element_type 은 덮어쓰지 않는다",
        fixed[0].element_type == "TEXT_LINE" and fixed[1].element_type == "HEADING",
        f"결과={[u.element_type for u in fixed]}",
    )


# =============================================================================
# 8. 경계 입력
# =============================================================================


def test_edge_cases() -> None:
    check("빈 목록", chunk_units([]) == [])
    check("공백만 있는 단위", chunk_units([TextUnit(text="   ")]) == [])
    check("머리글만 있는 문서", chunk_units([TextUnit(text="쪽", element_type="HEADER_FOOTER")]) == [])
    single = chunk_units([TextUnit(text="한 줄뿐인 문서다.")], min_tokens=1)
    check("한 줄뿐인 문서", len(single) == 1 and single[0].seq == 0)
    check("빈 평문", units_from_plain_text("") == [])
    check("줄바꿈만 있는 평문", units_from_plain_text("\n\n\n") == [])

    counter = CharRatioTokenCounter()
    check("빈 문자열 토큰 0", counter.count("") == 0)
    check("한 글자 토큰 1 이상", counter.count("가") >= 1)

    try:
        chunk_units([TextUnit(text="가")], max_tokens=0)
        check("max_tokens=0 은 거부", False)
    except ValueError:
        check("max_tokens=0 은 거부", True)

    try:
        chunk_units([TextUnit(text="가")], max_tokens=10, overlap_tokens=10)
        check("overlap >= max 는 거부", False)
    except ValueError:
        check("overlap >= max 는 거부", True)


# =============================================================================
# 실행
# =============================================================================

if __name__ == "__main__":
    # pytest 없이도 돌게 하려고 직접 부른다. 이 레포의 개발 컨테이너에는
    # pytest 가 없을 수 있어서다. pytest 로 돌리면 아래 블록은 실행되지 않고
    # 각 test_* 함수가 개별 테스트로 수집된다.
    tests = [
        test_plain_text,
        test_drop_header_footer,
        test_table,
        test_two_tables_separate,
        test_long_line,
        test_no_space_long_line,
        test_merge_short,
        test_last_short_chunk_kept,
        test_overlap,
        test_fallback_when_no_structure,
        test_respect_existing_structure,
        test_edge_cases,
    ]
    failures: list[str] = []
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append(f"{fn.__name__}: {exc}")

    print(f"검사 {len(PASS)}개 통과 · 실패한 테스트 {len(failures)}개")
    if failures:
        print("\n실패 목록")
        for f in failures:
            print("  -", f)

    chunks = chunk_units(
        units_from_plain_text(NOTICE, page_number=1),
        max_tokens=120,
        min_tokens=20,
        overlap_tokens=0,
    )
    print("\n=== 공고문 샘플 청킹 결과 (max_tokens=120) ===")
    for c in chunks:
        head = f"[{c.heading}] " if c.heading else ""
        span = (
            f"{c.content_start}~{c.content_end}"
            if c.content_start is not None
            else "구간없음"
        )
        preview = c.text.replace("\n", " / ")
        if len(preview) > 78:
            preview = preview[:78] + "…"
        print(f"  seq={c.seq} tok={c.token_count:3d} char={c.char_count:3d} {span:>10}  {head}{preview}")

    sys.exit(1 if failures else 0)
