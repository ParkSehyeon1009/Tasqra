# =============================================================================
# 이 파일의 책임: HTML 산출물을 검증한다. DB·파일이 필요 없다.
#
#   검사하는 것
#     ① **두 형식이 같은 절을 담는가** — 한쪽에만 절을 더하는 실수를 잡는다
#     ② 값을 escape 하는가 (보안. 문서 이름에 <script> 가 올 수 있다)
#     ③ 표가 없는 절(개요)과 행이 없는 표를 문장으로 내는가
#     ④ 형식별 확장자·MIME 이 한 곳에서 나오는가
#
# 다른 파일과의 관계
#   services/deliverable_html.py       검사 대상
#   services/deliverable_markdown.py   문서 구조와 Markdown 포매터
#   schemas/deliverable.py             FORMAT_FILE_TYPES
#
# Spring 비교: 같은 모델을 다른 View 로 그린 결과를 비교하는 뷰 테스트다.
# =============================================================================

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.schemas.deliverable import (
    FORMAT_FILE_TYPES,
    SUPPORTED_DELIVERABLE_FORMATS,
)
from app.services.deliverable_html import render_html
from app.services.deliverable_markdown import (
    DeliverableMaterials,
    build_document,
    render_markdown,
)

WEEK = {"period_from": date(2026, 8, 14), "period_to": date(2026, 8, 20)}


def _document(name="계약서.pdf"):
    return SimpleNamespace(
        filename=name,
        document_type="CONTRACT",
        created_at=datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc),
    )


def _amount():
    return SimpleNamespace(
        item_name="직접인건비",
        quantity=Decimal("6.0000"),
        unit_price=1_000_000,
        amount=6_000_000,
    )


def _args(materials=None, kind="WEEKLY_REPORT"):
    return {
        "kind": kind,
        "title": "주간 보고서 2026-08-14 ~ 2026-08-20",
        "period_from": WEEK["period_from"],
        "period_to": WEEK["period_to"],
        "materials": materials or DeliverableMaterials(documents=[_document()]),
        "generated_at_text": "2026-08-24 15:00",
    }


# --- ① 두 형식이 같은 절을 담는다 -------------------------------------------


def test_both_formats_have_the_same_sections():
    """절을 고르는 규칙은 한 곳(build_document)에만 있어야 한다."""
    args = _args(
        DeliverableMaterials(documents=[_document()], amount_items=[_amount()])
    )
    titles = [section.title for section in build_document(**args).sections]
    html, markdown = render_html(**args), render_markdown(**args)
    for title in titles:
        assert f"<h2>{title}</h2>" in html, title
        assert f"## {title}" in markdown, title
    # 주간 보고서는 개요 + 다섯 절이다.
    assert titles == ["개요", "문서", "완료한 태스크", "결정사항", "일정·기한", "금액"]


def test_meeting_agenda_has_only_decisions_in_both_formats():
    args = _args(DeliverableMaterials(), kind="MEETING_AGENDA")
    html, markdown = render_html(**args), render_markdown(**args)
    assert "<h2>결정사항</h2>" in html
    assert "<h2>문서</h2>" not in html
    assert "## 문서" not in markdown


def test_html_contains_real_values():
    args = _args(
        DeliverableMaterials(documents=[_document("과업지시서.pdf")], amount_items=[_amount()])
    )
    html = render_html(**args)
    assert "과업지시서.pdf" in html
    assert "직접인건비" in html
    # 금액 표기는 형식과 무관하다 — 문서 구조에서 이미 정해진다.
    assert "6,000,000" in html
    assert "<title>주간 보고서 2026-08-14 ~ 2026-08-20</title>" in html


# --- ② escape (보안) ---------------------------------------------------------


def test_html_escapes_values():
    """문서 이름은 사용자가 올린 파일에서 온 값이다. 태그가 살아 있으면 실행된다."""
    args = _args(DeliverableMaterials(documents=[_document("<script>alert(1)</script>.pdf")]))
    html = render_html(**args)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_html_escapes_title():
    args = _args()
    args["title"] = "보고서 <b>강조</b>"
    html = render_html(**args)
    assert "<b>강조</b>" not in html
    assert "&lt;b&gt;" in html


def test_html_keeps_pipe_as_is():
    """`|` 는 Markdown 표만 깨뜨린다. HTML 에서는 바꿀 이유가 없다."""
    args = _args(DeliverableMaterials(documents=[_document("A|B.pdf")]))
    assert "A|B.pdf" in render_html(**args)


# --- ③ 빈 절 ----------------------------------------------------------------


def test_empty_table_becomes_sentence_not_empty_table():
    """머리글만 있는 표는 '자료를 못 가져온 것' 처럼 보인다."""
    html = render_html(**_args(DeliverableMaterials(documents=[_document()])))
    assert "이 기간에 완료한 태스크가 없습니다." in html
    # 빈 표를 그리지 않는다 — 표는 자료가 있는 절에만 있다.
    assert html.count("<table>") == 1


def test_summary_section_is_a_paragraph():
    html = render_html(**_args())
    assert "<h2>개요</h2>" in html
    assert 'class="note"' in html


def test_html_is_a_whole_document():
    """산출물은 파일 하나로 주고받는다. 외부 CSS 를 참조하면 받는 쪽에서 깨진다."""
    html = render_html(**_args())
    assert html.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in html
    assert "<style>" in html
    assert "http://" not in html and "https://" not in html
    assert html.rstrip().endswith("</html>")


# --- ④ 형식 메타 -------------------------------------------------------------


def test_supported_formats_have_file_types():
    """만들 수 있는 형식은 확장자와 MIME 이 정의돼 있어야 한다."""
    for name in SUPPORTED_DELIVERABLE_FORMATS:
        assert name in FORMAT_FILE_TYPES, name
        extension, media_type = FORMAT_FILE_TYPES[name]
        assert extension and media_type


def test_markdown_and_html_have_different_file_types():
    assert FORMAT_FILE_TYPES["MD"][0] == "md"
    assert FORMAT_FILE_TYPES["HTML"][0] == "html"
    assert "markdown" in FORMAT_FILE_TYPES["MD"][1]
    assert "text/html" in FORMAT_FILE_TYPES["HTML"][1]
