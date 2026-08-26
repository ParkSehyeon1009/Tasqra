# =============================================================================
# 이 파일의 책임: 산출물 문서 구조(DeliverableDocument)를 XLSX 바이트로 바꾼다.
#   절을 고르는 규칙은 여기 없다 — deliverable_markdown.build_document 가 정한다.
#   MD·HTML 과 달리 **문자열이 아니라 bytes 를 돌려준다** — XLSX 는 zip 컨테이너라
#   텍스트로 다룰 수 없다(deliverable_service._write_file 이 이 둘을 나눠 쓴다).
#
# 다른 파일과의 관계
#   services/deliverable_markdown.py  문서 구조(DeliverableDocument)와 그 빌더
#   services/deliverable_html.py      같은 구조를 HTML 로 그린다 (형제 파일)
#   services/deliverable_service.py   RENDERERS["XLSX"] 로 이 함수를 부른다
#   schemas/deliverable.py            FORMAT_FILE_TYPES["XLSX"] 의 확장자·MIME
#
# Spring 비교: 같은 모델을 다른 View 로 그리는 것은 HTML 과 같다. 다만 Apache POI
#   의 Workbook 처럼 openpyxl 의 Workbook 이 파일 전체를 메모리에 들고 있다가
#   save() 에서 한 번에 굳는다 — ByteArrayOutputStream 에 쓰는 것과 같다.
#
# ⚠ 절이 비어도 시트를 만든다 — 이게 이 파일의 핵심 규칙이다
#   "행이 있는 절만 시트로" 만들면 자료가 없는 주에 **파일을 열었을 때 절이
#   사라진다.** 보고서를 받는 사람은 그것을 "빠뜨렸다" 로 읽는다. 그래서 표가 있는
#   절은 행이 0건이어도 시트를 만들고 머리글과 «없습니다» 문장을 함께 넣는다.
#   HTML·MD 가 빈 절에도 문장을 적는 것과 같은 판단이다.
#
# ⚠ 요약 시트를 반드시 채운다
#   엑셀은 **첫 시트를 열어서 보여준다.** 제목 세 줄만 있는 시트가 먼저 보이면
#   파일이 비어 보인다. 그래서 요약 시트에 제목·기간·개요와 함께 **어느 시트에
#   무엇이 몇 건 있는지** 표로 적는다. 시트 탭을 하나씩 눌러보지 않아도 된다.
#
# ⚠ 금액·수량은 문자열이 아니라 숫자로 넣는다
#   XLSX 를 고르는 이유가 «표 계산과 편집» 이다. "6,000,000" 이 글자로 들어가면
#   합계가 안 나와서 형식을 고른 이유가 없어진다. 그래서 머리글이 수량·단가·금액인
#   칸만 숫자로 되돌리고 표시 서식(#,##0)을 준다. **머리글로 판단하는 이유**는
#   값만 보고 바꾸면 "2026" 같은 제목이 숫자가 되기 때문이다.
#
# ⚠ 값을 escape 하지 않는다 — XLSX 에는 그 문제가 없다
#   Markdown 은 `|` 가 표를 깨고 HTML 은 `<` 가 태그가 된다. XLSX 셀 값은 그대로
#   들어가고 브라우저에서 실행되지 않아 이 형식만의 escape 규칙이 없다.
#
# ⚠ 색을 쓰지 않는다 — deliverable_html.py 와 같은 판단
#   머리글 배경(연회색)과 굵은 글씨, 얇은 테두리로만 구분한다.
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.services.deliverable_markdown import (
    EMPTY,
    NUMERIC_HEADERS,
    DeliverableDocument,
    build_document,
)

__all__ = ["render_xlsx", "to_xlsx"]

# 엑셀 시트 이름 제약: 31자 이하, `\ / ? * [ ] :` 금지.
_SHEET_NAME_LIMIT = 31
_INVALID_SHEET_CHARS = str.maketrans({character: " " for character in "\\/?*[]:"})

# 숫자로 되돌릴 칸은 머리글로 고른다. 그 목록은 deliverable_markdown 에 있다 —
# HTML 도 같은 목록으로 숫자 칸을 오른쪽에 맞추므로 두 형식이 갈리지 않는다.
_NUMERIC_TEXT = re.compile(r"^-?[\d,]+$")

_TITLE_FONT = Font(bold=True, size=15)
_META_FONT = Font(size=10, color="FF555555")
_NOTE_FONT = Font(size=10, color="FF555555", italic=True)
_SECTION_FONT = Font(bold=True, size=12)
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill(fill_type="solid", start_color="FFF2F2F2")
_THIN = Side(style="thin", color="FFBFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_TOP_LEFT = Alignment(wrap_text=True, vertical="top")
_HEADER_ALIGN = Alignment(vertical="center")

# 열 너비 상한·하한. 상한이 없으면 긴 파일명 한 개가 열을 화면 밖으로 밀어낸다.
_WIDTH_MIN = 10
_WIDTH_MAX = 48

# 한 줄 높이(엑셀 기본값). 줄바꿈되는 문장의 행 높이를 이 배수로 준다.
_LINE_HEIGHT = 15.0
# 요약 시트의 문단이 걸쳐 있는 대략적인 폭. 그 시트의 열 너비를 문단보다 나중에
# 정하므로 여기서는 값을 하나 가정한다 — 조금 넉넉하면 빈 줄이 생길 뿐이다.
_SUMMARY_NOTE_WIDTH = 55


def render_xlsx(**kwargs: Any) -> bytes:
    """산출물 본문을 XLSX 바이트로. 인자는 build_document 와 같다."""
    return to_xlsx(build_document(**kwargs))


def to_xlsx(document: DeliverableDocument) -> bytes:
    """문서 구조를 워크북으로 바꾸고 바이트로 굳힌다.

    시트 구성
      `요약`      제목·기간·개요 + «어느 시트에 무엇이 몇 건» 표
      절 이름별  표가 있는 절마다 하나. **0건이어도 만든다**(머리말 참고)

    표가 없는 절(개요처럼 문장만 있는 절)은 시트를 만들지 않고 요약 시트에
    문단으로 넣는다. 문장 한 줄짜리 시트를 늘리면 탭만 늘고 읽기 어려워진다.
    """
    workbook = Workbook()
    summary = workbook.active
    summary.title = "요약"

    # 표가 있는 절과 문장만 있는 절을 나눈다. 앞은 시트가 되고 뒤는 요약에 들어간다.
    table_sections = [section for section in document.sections if section.header]
    note_sections = [section for section in document.sections if not section.header]

    _write_summary(summary, document, table_sections, note_sections)

    for section in table_sections:
        sheet = workbook.create_sheet(_sheet_name(section.title, workbook))
        _write_table_sheet(sheet, section)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --- 요약 시트 ---------------------------------------------------------------


def _write_summary(
    sheet: Worksheet,
    document: DeliverableDocument,
    table_sections: list[Any],
    note_sections: list[Any],
) -> None:
    """첫 화면에 보이는 시트. 여기가 비면 파일 전체가 비어 보인다."""
    row = 1
    cell = sheet.cell(row=row, column=1, value=document.title)
    cell.font = _TITLE_FONT
    row += 2

    for line in document.meta:
        sheet.cell(row=row, column=1, value=line).font = _META_FONT
        row += 1
    row += 1

    # 개요처럼 문장만 있는 절. 제목을 함께 적어야 무슨 문장인지 알 수 있다.
    for section in note_sections:
        sheet.cell(row=row, column=1, value=section.title).font = _SECTION_FONT
        row += 1
        text = section.note or "해당 자료가 없습니다."
        cell = sheet.cell(row=row, column=1, value=text)
        cell.font = _NOTE_FONT
        cell.alignment = _TOP_LEFT
        # 병합해서 여러 열에 걸쳐 보이게 한다. 병합하지 않으면 옆 칸이 비어 있어도
        # 엑셀이 글자를 자르지 않지만, 아래 표와 열 경계가 어긋나 읽기 나쁘다.
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        # 병합한 칸은 엑셀이 높이를 자동으로 늘려주지 않는다. 직접 줄 수를 센다 —
        # 안 하면 긴 개요 문장이 한 줄만 보이고 나머지가 잘린다.
        sheet.row_dimensions[row].height = _note_height(text, _SUMMARY_NOTE_WIDTH)
        row += 2

    # 어느 시트에 무엇이 몇 건 있는지. 시트 탭을 하나씩 눌러보지 않게 하는 표다.
    sheet.cell(row=row, column=1, value="담긴 내용").font = _SECTION_FONT
    row += 1

    header_row = row
    for column, name in enumerate(("시트", "건수", "비고"), start=1):
        cell = sheet.cell(row=header_row, column=column, value=name)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = _HEADER_ALIGN
    row += 1

    widths = [_display_width(name) for name in ("시트", "건수", "비고")]
    for section in table_sections:
        count = len(section.rows)
        # 0건이면 왜 비었는지 문장을 함께 준다. 숫자만 있으면 "자료를 못 가져온 것"
        # 인지 "정말 없는 것" 인지 구분되지 않는다.
        note = "" if count else (section.note or "해당 자료가 없습니다.")
        values: list[Any] = [section.title, count, note]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            cell.border = _BORDER
            cell.alignment = _TOP_LEFT
            if column == 2:
                cell.number_format = "#,##0"
            widths[column - 1] = max(widths[column - 1], _display_width(value))
        row += 1

    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = _clamp_width(width)


# --- 절마다 하나씩 만드는 표 시트 ---------------------------------------------


def _write_table_sheet(sheet: Worksheet, section: Any) -> None:
    """표 한 절을 시트 하나로. **행이 0건이어도 머리글을 쓴다**(머리말 참고)."""
    header: list[str] = section.header
    for column, name in enumerate(header, start=1):
        cell = sheet.cell(row=1, column=column, value=name)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = _HEADER_ALIGN

    widths = [_display_width(name) for name in header]
    numeric = [name in NUMERIC_HEADERS for name in header]

    for offset, values in enumerate(section.rows):
        for column, raw in enumerate(values, start=1):
            value = _as_number(raw) if numeric[column - 1] else raw
            cell = sheet.cell(row=2 + offset, column=column, value=value)
            cell.border = _BORDER
            cell.alignment = _TOP_LEFT
            if isinstance(value, int):
                cell.number_format = "#,##0"
            widths[column - 1] = max(widths[column - 1], _display_width(raw))

    note_text = None
    if not section.rows:
        # 머리글만 있는 표는 "가져오기에 실패한 것" 처럼 보인다. 바로 아래 줄에
        # 없다고 적고 표 폭만큼 병합한다. **열 너비를 이 문장 때문에 늘리지 않는다** —
        # 병합이 폭을 해결하므로, 늘리면 자료가 들어온 주에 열이 쓸데없이 넓어진다.
        note_text = section.note or "해당 자료가 없습니다."
        cell = sheet.cell(row=2, column=1, value=note_text)
        cell.font = _NOTE_FONT
        cell.alignment = _TOP_LEFT
        if len(header) > 1:
            sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(header))

    final_widths = [_clamp_width(width) for width in widths]
    for column, width in enumerate(final_widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width

    if note_text is not None:
        # 열 너비를 정한 뒤에 높이를 센다 — 병합된 폭을 알아야 줄 수가 나온다.
        sheet.row_dimensions[2].height = _note_height(note_text, sum(final_widths))

    # 행이 많아도 머리글이 따라다니게 한다. 200행 상한(MATERIAL_ROW_LIMIT)까지 쌓인다.
    sheet.freeze_panes = "A2"


# --- 내부 -------------------------------------------------------------------


def _as_number(text: Any) -> Any:
    """"6,000,000" → 6000000. 숫자가 아니면 그대로 둔다.

    `EMPTY`(—)는 «값이 없다» 는 뜻이므로 0 으로 바꾸지 않는다 — 바꾸면 «0원» 과
    구별되지 않는다(deliverable_markdown.money 와 같은 판단).
    """
    if not isinstance(text, str) or text == EMPTY:
        return text
    stripped = text.strip()
    if not _NUMERIC_TEXT.match(stripped):
        return text
    try:
        return int(stripped.replace(",", ""))
    except ValueError:
        return text


def _display_width(value: Any) -> int:
    """엑셀 열 너비 계산용 글자 폭. 한글·한자는 두 칸으로 센다.

    `len()` 만 쓰면 한글 제목이 담긴 열이 절반 너비로 잡혀 잘려 보인다.
    """
    text = str(value)
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def _clamp_width(width: int) -> int:
    """너무 좁거나 넓지 않게. 상한이 없으면 긴 파일명 하나가 열을 밀어낸다."""
    return max(_WIDTH_MIN, min(_WIDTH_MAX, width + 2))


def _note_height(text: str, merged_width: int) -> float:
    """줄바꿈되는 문장이 들어간 행의 높이.

    병합한 칸은 엑셀이 높이를 자동으로 늘려주지 않아서 직접 줄 수를 센다.
    """
    usable = max(20, merged_width)
    lines = max(1, -(-_display_width(text) // usable))
    return _LINE_HEIGHT * lines


def _sheet_name(title: str, workbook: Workbook) -> str:
    """시트 이름을 엑셀 규칙(31자, 금지문자)에 맞춘다.

    지금 절 이름(문서·완료한 태스크·결정사항·일정·기한·금액)은 다 짧고 서로
    다르지만, 절이 늘어날 때를 위해 중복이면 번호를 붙인다.
    """
    cleaned = title.translate(_INVALID_SHEET_CHARS).strip() or "절"
    name = cleaned[:_SHEET_NAME_LIMIT]
    if name not in workbook.sheetnames:
        return name
    for suffix in range(2, 100):
        candidate = f"{cleaned[: _SHEET_NAME_LIMIT - 3]}_{suffix}"
        if candidate not in workbook.sheetnames:
            return candidate
    return name
