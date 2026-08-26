# =============================================================================
# 이 파일의 책임: XLSX 산출물을 검증한다. DB·파일이 필요 없다.
#
#   검사하는 것
#     ① 반환이 bytes 이고 진짜 XLSX(zip) 인가 — MD·HTML 과 다른 계약이다
#     ② **빈 절도 시트가 생기는가** — 자료 없는 주에 절이 사라지던 버그의 회귀
#     ③ 금액·수량이 문자열이 아니라 **숫자**로 들어가고 서식이 #,##0 인가
#        (XLSX 를 고르는 이유가 «표 계산» 이라 여기가 깨지면 형식 의미가 없다)
#     ④ 값이 없는 칸(—)이 **0 으로 바뀌지 않는가**
#     ⑤ 요약 시트에 «담긴 내용»(어느 시트에 몇 건) 표가 있는가
#     ⑥ 회의 안건은 결정사항 시트만 갖는가 (build_document 규칙을 그대로 따르는가)
#     ⑦ 시트 이름이 엑셀 규칙(31자·금지문자·중복 번호)을 지키는가
#
# 다른 파일과의 관계
#   services/deliverable_xlsx.py       검사 대상
#   services/deliverable_markdown.py   문서 구조와 Section·DeliverableDocument
#
# Spring 비교: 뷰가 만든 산출물(POI Workbook)을 다시 로드해 셀을 읽어 보는 뷰
#   테스트다. test_deliverable_html.py 가 HTML 문자열을 검사하는 것과 짝이다.
#
# ⚠ 검사 방법: **만든 바이트를 openpyxl 로 되읽어서** 셀을 본다. 만드는 코드가
#   내부에서 무엇을 하든, 실제로 열었을 때의 결과만 본다 — 사용자가 엑셀에서
#   여는 것과 같은 관점이다.
# =============================================================================

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.deliverable_markdown import (
    EMPTY,
    DeliverableDocument,
    DeliverableMaterials,
    Section,
)
from app.services.deliverable_xlsx import render_xlsx, to_xlsx

WEEK = {"period_from": date(2026, 8, 14), "period_to": date(2026, 8, 20)}

# 주간 보고서의 절 이름. build_document 가 정한 순서와 같아야 한다.
WEEKLY_SECTIONS = ["문서", "완료한 태스크", "결정사항", "일정·기한", "금액"]


def _document(name="계약서.pdf"):
    return SimpleNamespace(
        filename=name,
        document_type="CONTRACT",
        created_at=datetime(2026, 8, 17, 9, 30, tzinfo=timezone.utc),
    )


def _amount(name="직접인건비", quantity=Decimal("6.0000"), unit_price=1_000_000, amount=6_000_000):
    return SimpleNamespace(
        item_name=name,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
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


def _load(data):
    """만든 바이트를 되읽는다. 실제로 엑셀에서 여는 것과 같은 관점이다."""
    return load_workbook(BytesIO(data))


def _find_row(sheet, first_cell_value):
    """첫 칸이 주어진 값인 행을 찾아 그 행의 값 리스트를 돌려준다. 없으면 None."""
    for row in sheet.iter_rows(values_only=True):
        if row and row[0] == first_cell_value:
            return list(row)
    return None


# --- ① 반환 계약 ------------------------------------------------------------


def test_render_returns_xlsx_bytes():
    """MD·HTML 은 str, XLSX 는 bytes 다. _write_file 이 이 차이로 wb/w 를 고른다."""
    data = render_xlsx(**_args())
    assert isinstance(data, bytes)
    # XLSX 는 zip 컨테이너다. zip 은 'PK' 로 시작한다.
    assert data[:2] == b"PK"


# --- ② 빈 절도 시트가 생긴다 (회귀) -----------------------------------------


def test_empty_sections_still_become_sheets():
    """자료가 문서 1건뿐이어도 다섯 절 시트가 모두 있어야 한다.

    '행이 있는 절만 시트로' 만들면 자료 없는 주에 절이 통째로 사라진다 — 받는
    사람은 그것을 '빠뜨렸다' 로 읽는다. 이 버그를 잡는 회귀 테스트다.
    """
    workbook = _load(render_xlsx(**_args(DeliverableMaterials(documents=[_document()]))))
    assert workbook.sheetnames == ["요약", *WEEKLY_SECTIONS]


def test_empty_section_sheet_has_header_and_sentence():
    """0건인 절 시트도 머리글과 '없습니다' 문장을 갖는다 — 빈 시트로 두지 않는다."""
    workbook = _load(render_xlsx(**_args(DeliverableMaterials(documents=[_document()]))))
    sheet = workbook["완료한 태스크"]
    # 1행은 머리글.
    assert [c.value for c in sheet[1]][:3] == ["제목", "담당", "완료일"]
    # 2행에 없다는 문장.
    assert sheet.cell(row=2, column=1).value == "이 기간에 완료한 태스크가 없습니다."


# --- ③ 금액·수량은 숫자로 -----------------------------------------------------


def test_amounts_are_numbers_not_text():
    """'6,000,000' 이 글자로 들어가면 합계가 안 된다. 정수 + #,##0 서식이어야 한다."""
    workbook = _load(
        render_xlsx(**_args(DeliverableMaterials(amount_items=[_amount()], documents=[_document()])))
    )
    sheet = workbook["금액"]
    assert [c.value for c in sheet[1]] == ["항목", "수량", "단가", "금액"]
    # 2행: 항목명(문자열) · 수량 6 · 단가 1,000,000 · 금액 6,000,000 — 뒤 셋은 정수.
    assert sheet.cell(row=2, column=1).value == "직접인건비"
    unit_price = sheet.cell(row=2, column=3)
    amount = sheet.cell(row=2, column=4)
    assert unit_price.value == 1_000_000 and isinstance(unit_price.value, int)
    assert amount.value == 6_000_000 and isinstance(amount.value, int)
    assert amount.number_format == "#,##0"


def test_item_name_is_not_coerced_to_number():
    """항목명은 숫자 칸이 아니다. 숫자처럼 생긴 이름도 문자열로 남아야 한다."""
    workbook = _load(
        render_xlsx(
            **_args(
                DeliverableMaterials(
                    amount_items=[_amount(name="2026")], documents=[_document()]
                )
            )
        )
    )
    cell = workbook["금액"].cell(row=2, column=1)
    assert cell.value == "2026" and isinstance(cell.value, str)


# --- ④ 값 없음(—)은 0 이 아니다 ----------------------------------------------


def test_empty_value_stays_dash_not_zero():
    """단가가 없는 항목은 '—' 로 남는다. 0 으로 바꾸면 '0원' 과 구별되지 않는다."""
    workbook = _load(
        render_xlsx(
            **_args(
                DeliverableMaterials(
                    amount_items=[_amount(unit_price=None, amount=None)],
                    documents=[_document()],
                )
            )
        )
    )
    sheet = workbook["금액"]
    assert sheet.cell(row=2, column=3).value == EMPTY
    assert sheet.cell(row=2, column=4).value == EMPTY


# --- ⑤ 요약 시트 -------------------------------------------------------------


def test_summary_sheet_lists_each_section_with_count():
    """요약 시트에 '담긴 내용' 표가 있고, 절마다 건수가 적혀야 한다."""
    materials = DeliverableMaterials(
        documents=[_document(), _document("제안서.pdf")],
        amount_items=[_amount()],
    )
    workbook = _load(render_xlsx(**_args(materials)))
    summary = workbook["요약"]
    texts = [v for row in summary.iter_rows(values_only=True) for v in row if isinstance(v, str)]
    assert "담긴 내용" in texts
    # 문서 2건 · 금액 1건이 표에 그대로 나온다.
    assert _find_row(summary, "문서")[:2] == ["문서", 2]
    assert _find_row(summary, "금액")[:2] == ["금액", 1]
    # 0건인 절도 표에 남고, 비고에 이유 문장이 붙는다.
    tasks_row = _find_row(summary, "완료한 태스크")
    assert tasks_row[1] == 0
    assert "없습니다" in (tasks_row[2] or "")


def test_summary_title_and_meta_are_present():
    workbook = _load(render_xlsx(**_args()))
    summary = workbook["요약"]
    assert summary.cell(row=1, column=1).value == "주간 보고서 2026-08-14 ~ 2026-08-20"
    # 기간·만든 시각 메타가 어딘가에 있다.
    joined = "\n".join(
        str(v)
        for row in summary.iter_rows(values_only=True)
        for v in row
        if v is not None
    )
    assert "대상 기간" in joined and "만든 시각" in joined


# --- ⑥ 유형별 절 (build_document 규칙) ---------------------------------------


def test_meeting_agenda_has_only_decisions_sheet():
    """회의 안건은 결정만 담는다 — 문서·금액 시트가 없어야 한다."""
    workbook = _load(render_xlsx(**_args(DeliverableMaterials(), kind="MEETING_AGENDA")))
    assert workbook.sheetnames == ["요약", "결정사항"]


# --- ⑦ 시트 이름 규칙 --------------------------------------------------------


def _doc_with_sections(*sections):
    """시트 이름 규칙만 보려고 제목을 직접 지은 문서를 만든다."""
    return DeliverableDocument(
        title="제목",
        meta=["대상 기간: 기간 전체"],
        sections=list(sections),
    )


def test_sheet_name_strips_forbidden_chars():
    """엑셀은 \\ / ? * [ ] : 를 시트 이름에 못 쓴다. 그대로 넣으면 파일이 깨진다."""
    document = _doc_with_sections(
        Section(title="금액/원가[안]", header=["항목"], rows=[["직접비"]])
    )
    workbook = _load(to_xlsx(document))
    made = [name for name in workbook.sheetnames if name != "요약"]
    assert made == ["금액 원가 안 "] or made == ["금액 원가 안"], made
    for bad in "\\/?*[]:":
        assert all(bad not in name for name in workbook.sheetnames)


def test_sheet_name_truncated_to_31_chars():
    long_title = "가" * 40
    document = _doc_with_sections(
        Section(title=long_title, header=["항목"], rows=[["x"]])
    )
    workbook = _load(to_xlsx(document))
    assert all(len(name) <= 31 for name in workbook.sheetnames)


def test_duplicate_sheet_names_get_numbered():
    """같은 이름이 둘이면 번호를 붙인다 — openpyxl 이 중복 이름을 거부한다."""
    document = _doc_with_sections(
        Section(title="금액", header=["항목"], rows=[["a"]]),
        Section(title="금액", header=["항목"], rows=[["b"]]),
    )
    workbook = _load(to_xlsx(document))
    sheets = [name for name in workbook.sheetnames if name != "요약"]
    assert len(sheets) == 2
    assert len(set(sheets)) == 2  # 서로 다른 이름
