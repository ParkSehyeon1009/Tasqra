# =============================================================================
# 이 파일의 책임: 산출물 문서 구조를 HTML 한 장으로 바꾼다. 절을 고르는 규칙은
#   여기 없다 — deliverable_markdown.build_document 가 정한다.
#
# 다른 파일과의 관계
#   services/deliverable_markdown.py  문서 구조(DeliverableDocument)와 그 빌더
#   services/deliverable_xlsx.py      같은 구조를 XLSX 로 그린다 (형제 파일)
#   services/deliverable_service.py   형식에 따라 이 함수나 render_markdown 을 부른다
#
# Spring 비교: 같은 모델을 다른 View 로 그리는 것이다(JSON 뷰 대 HTML 뷰).
#
# ⚠ 값을 반드시 escape 한다 — 보안 문제다
#   문서 이름이나 항목명은 **사용자가 올린 파일에서 온 값**이다. 거기에
#   `<script>` 가 들어 있으면 HTML 산출물을 브라우저로 열 때 그대로 실행된다.
#   그래서 모든 칸을 html.escape 로 감싼다. Markdown 은 `|` 를 막았지만 그것은
#   표가 깨지는 문제였고, 이쪽은 실행되는 문제라 성격이 다르다.
#
#   다운로드도 첨부(attachment)로 내려간다 — FileResponse 에 filename 을 주면
#   Content-Disposition 이 attachment 가 되어 브라우저가 우리 도메인에서 바로
#   렌더링하지 않는다. escape 와 함께 두 겹이다.
#
# ⚠ 왜 HTML 만 꾸미는가 (2026-08-26 판단)
#   `XLSX`·`MD` 는 **받아서 더 가공하는** 형식이다. 셀 배경이나 글꼴을 넣으면
#   붙여 쓸 때 오히려 방해가 되므로 무채색·최소 서식으로 둔다.
#   `HTML`·`PDF` 는 **그대로 보내고 그대로 인쇄하는** 형식이다(PDF 는 이 HTML 을
#   그대로 구워 만든다 — deliverable_pdf.py).
#   그래서 이 파일만 표지·절 번호·머리글 대비 같은 짜임을 갖는다.
#
# ⚠ 포인트색 하나만 쓴다 — 나머지는 무채색이다 (2026-08-27 판단)
#   전에는 완전 무채색이었는데 검정 면(표지 띠·번호 뱃지·표 머리)이 너무 무거웠고,
#   표지만 화면 폭 전체라 본문(가운데 컬럼)과 왼쪽이 어긋났다. 그래서 검정 면을
#   걷어내고 **포인트색 #0f6b6b(딥 틸) 하나**만 쓴다 — 표지 아래 선 하나와 절 번호
#   칩에만. 전체 폭 가로선을 절·표마다 반복하면 조잡해져서("선이 줄줄줄") 표지 아래
#   한 줄로만 두고, 나머지 위계는 **여백과 글자 크기**로 만든다. 나머지 색은 여전히
#   검정(#1b1b1b)·회색·흰색이다.
#
#   색을 바꾸려면 이 파일의 #0f6b6b 를 모두 바꾼다(지금은 그 한 값뿐이다). CSS
#   변수를 쓰지 않는 이유는 아래 STYLE 주석 참고 — 오래된 PDF 엔진 대비다.
#   포인트색은 채도·명도가 있어 흑백 복사에서도 회색으로 남아 뭉개지지 않는다.
#   스타일은 파일 안에 넣는다 — 산출물은 한 파일로 주고받으므로 외부 CSS·웹폰트를
#   참조하면 받는 쪽에서 깨진다.
#
# ⚠ 마크업을 바꿀 때 테스트를 먼저 본다
#   test_deliverable_html.py 가 `<h2>{절 제목}</h2>` 와 `<table>` 을 **속성 없이
#   그대로** 찾는다(두 형식이 같은 절을 담는지, 빈 표를 그리지 않는지 검사한다).
#   그래서 절 번호는 `<h2>` **밖에** 두고 표에는 class 를 붙이지 않는다. 꾸미는
#   것은 바깥 요소와 CSS 선택자로 한다.
# =============================================================================

from __future__ import annotations

from html import escape
from typing import Any

from app.services.deliverable_markdown import (
    NUMERIC_HEADERS,
    DeliverableDocument,
    build_document,
)

__all__ = ["render_html", "to_html"]

# 무채색 + 포인트색 하나(#0f6b6b). 폰트는 받는 쪽에 있는 것을 쓴다(웹폰트를
# 내려받게 하지 않는다).
#
# CSS 변수(--foo)를 쓰지 않았다. 나중에 PDF 변환기를 붙일 때 오래된 엔진이
# 변수를 이해하지 못하면 색이 전부 빠진다 — 값을 그대로 적어 두면 그런 일이 없다.
# 그래서 포인트색은 #0f6b6b 리터럴로 반복된다. 색을 바꾸려면 전부 찾아 바꾼다.
STYLE = """
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { margin: 0; background: #ffffff; color: #1b1b1b; font-size: 14px; line-height: 1.65;
  font-family: -apple-system, "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo",
    "NanumGothic", "Nanum Gothic", sans-serif; }

/* 표지. 검정 면을 걷어내고 흰 바탕에 제목 블록 아래 포인트색 선 하나만 둔다.
   본문·꼬리말과 같은 920px 가운데 컬럼에 두어 왼쪽 끝을 맞춘다 — 전에는 표지만
   화면 폭 전체라 가운데 정렬된 본문과 왼쪽이 어긋나 표지만 튀어 보였다.
   전체 폭 가로선은 이 한 줄뿐이다 — 절·표마다 선을 반복하면 "선이 줄줄줄" 조잡해져서,
   나머지 위계는 선이 아니라 여백과 글자 크기로 만든다. */
.cover { max-width: 920px; margin: 0 auto; padding: 38px 44px 20px;
  border-bottom: 3px solid #0f6b6b; }
.cover h1 { margin: 0; font-size: 27px; font-weight: 700; line-height: 1.3;
  letter-spacing: -0.01em; color: #1b1b1b; }
/* 메타는 가운뎃점(·)으로 잇는다 — 점 마커를 줄줄이 붙이면 그것도 선처럼 보인다. */
.cover .meta { display: flex; flex-wrap: wrap; margin: 15px 0 0; padding: 0;
  list-style: none; color: #6a6a6a; font-size: 12px; }
.cover .meta li:not(:last-child)::after { content: "·"; margin: 0 10px; color: #c4c4c4; }

main { max-width: 920px; margin: 0 auto; padding: 26px 44px 4px; }

/* 절 머리. keyline 을 두지 않고 여백으로 절을 나눈다. 번호는 작은 포인트색 칩,
   제목은 굵게. 위계를 선이 아니라 .block 위 여백과 글자로 드러낸다. */
.block { margin: 32px 0 0; }
.block-head { display: flex; align-items: center; gap: 10px; margin: 0 0 12px; }
.block-num { flex: none; min-width: 22px; padding: 3px 6px; background: #0f6b6b; color: #ffffff;
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-align: center; border-radius: 2px; }
.block-head h2 { margin: 0; font-size: 16px; font-weight: 700; letter-spacing: 0.01em; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
/* 표 머리. 검정 면도 포인트색 밑선도 없이 연회색 바탕만으로 구분한다 — 표 안의 얇은
   행선은 데이터를 읽는 격자라 남기지만, 강조하는 가로선은 두지 않는다. */
thead th { padding: 9px 11px; background: #f4f4f4; color: #5a5a5a;
  font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-align: left; white-space: nowrap; }
tbody td { padding: 9px 11px; border-bottom: 1px solid #eeeeee; vertical-align: top; }
tbody tr:nth-child(even) td { background: #fafafa; }
/* 숫자 칸. 오른쪽으로 맞추고 자릿수 폭을 고정해 금액이 나란히 읽히게 한다. */
.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }

/* 자료가 없는 절과 개요. 선 대신 연회색 면으로 문장을 감싼다(왼쪽 선을 두지 않는다). */
p.note { margin: 0; padding: 14px 16px; background: #f5f5f5; color: #4a4a4a;
  font-size: 13px; border-radius: 3px; }

footer { max-width: 920px; margin: 0 auto; padding: 22px 44px 42px; }
footer p { margin: 0; color: #8a8a8a; font-size: 11px; }

@media print {
  @page { margin: 14mm; }
  body { font-size: 10.5pt; }
  .cover, main, footer { max-width: none; padding-left: 24px; padding-right: 24px; }
  .cover { padding-top: 22px; padding-bottom: 16px; }
  /* 절과 행이 페이지 경계에서 잘리지 않게. 머리글은 다음 장에도 따라간다. */
  .block { page-break-inside: avoid; }
  thead { display: table-header-group; }
  tr { page-break-inside: avoid; }
}
""".strip()


def render_html(**kwargs: Any) -> str:
    """산출물 본문을 HTML 로. 인자는 build_document 와 같다."""
    return to_html(build_document(**kwargs))


def to_html(document: DeliverableDocument) -> str:
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(document.title)}</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        '<header class="cover">',
        f"<h1>{escape(document.title)}</h1>",
    ]

    if document.meta:
        parts.append('<ul class="meta">')
        parts.extend(f"<li>{escape(line)}</li>" for line in document.meta)
        parts.append("</ul>")
    parts.append("</header>")

    parts.append("<main>")
    for number, section in enumerate(document.sections, start=1):
        parts.append('<section class="block">')
        # 번호를 h2 밖에 두는 이유는 파일 머리말 참고(테스트가 h2 를 그대로 찾는다).
        parts.append('<div class="block-head">')
        parts.append(f'<span class="block-num">{number:02d}</span>')
        parts.append(f"<h2>{escape(section.title)}</h2>")
        parts.append("</div>")

        if section.header and section.rows:
            parts.extend(_table(section.header, section.rows))
        else:
            # 표가 없는 절(개요)과 행이 없는 표는 같은 모양으로 문장만 낸다.
            # 빈 표를 그리면 "자료를 못 가져온 것" 처럼 보인다.
            note = section.note or "해당 자료가 없습니다."
            parts.append(f'<p class="note">{escape(note)}</p>')
        parts.append("</section>")
    parts.append("</main>")

    # 꼬리말. 인쇄해서 나눠줬을 때 어느 문서의 몇 시 기준인지 남는다.
    colophon = " · ".join([document.title, *document.meta])
    parts.extend(["<footer>", f"<p>{escape(colophon)}</p>", "</footer>"])

    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    """표 하나. `<table>` 에 속성을 붙이지 않는다 — 파일 머리말 참고.

    숫자 칸만 `class="num"` 으로 오른쪽에 맞춘다. 어느 칸이 숫자인지는 머리글로
    판단하고 그 목록은 `deliverable_markdown.NUMERIC_HEADERS` 한 곳에 있다.
    """
    numeric = [name in NUMERIC_HEADERS for name in header]
    parts = ["<table>", "<thead><tr>"]
    parts.extend(
        f'<th class="num">{escape(name)}</th>' if numeric[index] else f"<th>{escape(name)}</th>"
        for index, name in enumerate(header)
    )
    parts.extend(["</tr></thead>", "<tbody>"])
    for row in rows:
        parts.append("<tr>")
        parts.extend(
            f'<td class="num">{escape(value)}</td>'
            if index < len(numeric) and numeric[index]
            else f"<td>{escape(value)}</td>"
            for index, value in enumerate(row)
        )
        parts.append("</tr>")
    parts.extend(["</tbody>", "</table>"])
    return parts
