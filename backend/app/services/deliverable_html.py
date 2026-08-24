# =============================================================================
# 이 파일의 책임: 산출물 문서 구조를 HTML 한 장으로 바꾼다. 절을 고르는 규칙은
#   여기 없다 — deliverable_markdown.build_document 가 정한다.
#
# 다른 파일과의 관계
#   services/deliverable_markdown.py  문서 구조(DeliverableDocument)와 그 빌더
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
# ⚠ 색을 쓰지 않는다
#   보고서는 흑백으로 만든다. 인쇄와 캡처에서 흐려지지 않고, 강조가 필요한 곳은
#   굵기와 선으로만 나타낸다. 스타일은 파일 안에 넣는다 — 산출물은 한 파일로
#   주고받으므로 외부 CSS 를 참조하면 받는 쪽에서 깨진다.
# =============================================================================

from __future__ import annotations

from html import escape
from typing import Any

from app.services.deliverable_markdown import DeliverableDocument, build_document

__all__ = ["render_html", "to_html"]

# 흑백 무채색. 폰트는 받는 쪽에 있는 것을 쓴다(웹폰트를 내려받게 하지 않는다).
STYLE = """
body { max-width: 900px; margin: 40px auto; padding: 0 20px;
  font-family: -apple-system, "Segoe UI", "Malgun Gothic", sans-serif;
  color: #1b1b1b; line-height: 1.6; }
h1 { margin: 0 0 6px; font-size: 24px; }
h2 { margin: 32px 0 10px; padding-bottom: 6px; font-size: 17px;
  border-bottom: 1px solid #1b1b1b; }
ul.meta { margin: 0 0 8px; padding-left: 18px; color: #555; font-size: 13px; }
p.note { color: #555; font-size: 14px; }
table { width: 100%; margin: 0; border-collapse: collapse; font-size: 14px; }
th, td { padding: 7px 9px; border: 1px solid #c9c9c9; text-align: left;
  vertical-align: top; }
th { background: #f2f2f2; font-weight: 700; }
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
        f"<title>{escape(document.title)}</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        f"<h1>{escape(document.title)}</h1>",
    ]

    if document.meta:
        parts.append('<ul class="meta">')
        parts.extend(f"<li>{escape(line)}</li>" for line in document.meta)
        parts.append("</ul>")

    for section in document.sections:
        parts.append(f"<h2>{escape(section.title)}</h2>")
        if section.header and section.rows:
            parts.append("<table>")
            parts.append("<thead><tr>")
            parts.extend(f"<th>{escape(name)}</th>" for name in section.header)
            parts.append("</tr></thead>")
            parts.append("<tbody>")
            for row in section.rows:
                parts.append("<tr>")
                parts.extend(f"<td>{escape(value)}</td>" for value in row)
                parts.append("</tr>")
            parts.append("</tbody>")
            parts.append("</table>")
        else:
            # 표가 없는 절(개요)과 행이 없는 표는 같은 모양으로 문장만 낸다.
            # 빈 표를 그리면 "자료를 못 가져온 것" 처럼 보인다.
            note = section.note or "해당 자료가 없습니다."
            parts.append(f'<p class="note">{escape(note)}</p>')

    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)
