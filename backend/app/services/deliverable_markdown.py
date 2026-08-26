# =============================================================================
# 이 파일의 책임: 산출물 본문을 (1) 형식과 무관한 문서 구조로 만들고,
#   (2) 그것을 Markdown 문자열로 바꾼다. DB·파일·HTTP 를 모른다.
#
# 다른 파일과의 관계
#   services/deliverable_html.py     같은 문서 구조를 HTML 로 바꾼다
#   services/deliverable_service.py  자료를 모아 이 함수를 부르고 파일로 저장한다
#   repositories/deliverable_repository.py  자료를 조회한다
#   schemas/deliverable.py  유형 이름(DELIVERABLE_KIND_LABELS)을 여기서도 쓴다
#
# Spring 비교: 템플릿 엔진(Thymeleaf·Freemarker) 자리다. 다만 템플릿 파일을 두지
#   않고 문서 구조 + 포매터로 나눴다 — 표 몇 개라 템플릿 문법을 더할 이유가 없고,
#   순수 함수라 DB 없이 테스트된다.
#
# ⚠ 왜 문서 구조를 따로 두는가 (형식이 둘이 된 뒤의 이유)
#   Markdown 과 HTML 이 각자 절을 만들면 **한쪽에만 절을 더하는 실수**가 생긴다.
#   금액 절을 MD 에만 넣고 HTML 에 빼먹어도 에러가 나지 않는다. 그래서
#   "유형마다 어떤 절이 들어가는가" 는 build_document 한 곳에만 둔다.
#   형식별 파일은 **표를 어떻게 그리는지**만 안다.
#
# ⚠ 값을 escape 하는 것은 **형식별 포매터의 몫**이다
#   Markdown 은 `|` 가 표를 깨고, HTML 은 `<` 가 태그가 된다. 막아야 하는 글자가
#   다르므로 구조에는 원래 값을 담고 각 포매터가 자기 규칙으로 바꾼다.
#   구조 단계에서 한쪽 규칙으로 바꿔 두면 다른 형식에서 값이 이상해진다.
#
# ⚠ 개요는 LLM 이 채운다 — 단, 이 파일은 채우지 않는다
#   DLV-002-1·DLV-002-2 완료 판정의 "LLM 호출은 개요 1회" 를 위해 개요 문장은
#   서비스(deliverable_service)가 LLM 을 1회 불러 만들고 `summary` 인자로 넘긴다.
#   이 파일은 받은 문장을 개요 절에 넣기만 한다(구조 함수는 DB·LLM 을 모른다).
#   `summary` 가 없으면(LLM 미연결·호출 실패) SUMMARY_PLACEHOLDER 로 되돌아간다 —
#   **없는 문장을 지어내지 않는다.** 표는 예나 지금이나 전부 실제 자료다.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas.deliverable import DELIVERABLE_KIND_LABELS

__all__ = [
    "EMPTY",
    "NUMERIC_HEADERS",
    "DeliverableDocument",
    "DeliverableMaterials",
    "Section",
    "build_document",
    "build_title",
    "clean",
    "render_markdown",
]

# 값이 없을 때 표에 넣는 글자. 0 과 구별한다.
EMPTY = "—"

# 숫자가 담기는 칸의 머리글. 형식별 포매터가 이것을 보고 다르게 그린다 —
# HTML 은 오른쪽으로 맞추고, XLSX 는 문자열을 숫자로 되돌려 합계가 되게 한다.
#
# **값이 아니라 머리글로 판단하는 이유**: 값만 보고 «숫자처럼 생겼으면 숫자» 로
# 다루면 "2026" 같은 제목이 숫자가 된다. 머리글은 build_document 가 정하므로
# 뜻이 분명하다.
#
# ⚠ 이 파일의 절 머리글을 바꾸면 여기도 바꿔야 한다. 안 바꿔도 에러는 나지 않고
#   **조용히 왼쪽 정렬·문자열로 남는다** — 그래서 한 곳에 모아 두었다.
NUMERIC_HEADERS = frozenset({"수량", "단가", "금액", "건수"})

SUMMARY_PLACEHOLDER = (
    "개요 문장은 아직 넣지 않았습니다. 저장된 문서 요약을 한 번 재요약해 채울"
    " 자리입니다(LLM 연결 예정). 아래 표는 모두 실제 자료입니다."
)


@dataclass
class DeliverableMaterials:
    """산출물에 담을 실제 행들.

    서비스가 리포지토리에서 받아 그대로 넣는다. 유형에 따라 비는 목록이 있다 —
    예를 들어 회의 안건은 결정만 담으므로 나머지가 빈 목록이다.
    """

    documents: list[Any] = field(default_factory=list)
    completed_tasks: list[Any] = field(default_factory=list)
    decisions: list[Any] = field(default_factory=list)
    schedule_items: list[Any] = field(default_factory=list)
    amount_items: list[Any] = field(default_factory=list)


@dataclass
class Section:
    """문서의 한 절.

    `header` 가 없으면 표가 아니라 문단이다(개요처럼). 표인데 `rows` 가 비면
    머리글만 있는 표 대신 `note` 문장을 쓴다 — 빈 표는 "자료를 못 가져온 것" 처럼
    보인다.
    """

    title: str
    header: list[str] | None = None
    rows: list[list[str]] = field(default_factory=list)
    note: str | None = None


@dataclass
class DeliverableDocument:
    """형식과 무관한 산출물 내용. 포매터가 이것만 보고 그린다."""

    title: str
    meta: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)


def clean(value: Any) -> str:
    """표 한 칸에 넣을 값을 다듬는다.

    None·빈 값은 —, 줄바꿈은 공백으로 바꾼다. 줄바꿈은 Markdown 에서 행을 갈라
    표를 깨고 HTML 에서도 의미가 없다.

    **형식별 escape 는 하지 않는다** — 파일 머리말 참고.
    """
    if value is None or value == "":
        return EMPTY
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def money(value: Decimal | int | None) -> str:
    """금액. 천 단위 구분을 넣는다. 없으면 — 다 (0 으로 바꾸지 않는다)."""
    if value is None:
        return EMPTY
    return f"{int(value):,}"


def day(value: date | None) -> str:
    return value.isoformat() if value else EMPTY


def build_title(kind: str, period_from: date | None, period_to: date | None) -> str:
    """제목. 기간이 있으면 붙인다.

    계약서 예시가 "주간 보고서 2026-08-04 ~ 2026-08-10" 이다. 기간을 쓰지 않는
    유형은 기간 대신 아무것도 붙이지 않는다 — 생성일을 붙이면 같은 내용을 두 번
    만들었을 때 제목만 달라져 이력에서 구별이 어려워진다.
    """
    label = DELIVERABLE_KIND_LABELS.get(kind, kind)
    if period_from and period_to:
        return f"{label} {period_from.isoformat()} ~ {period_to.isoformat()}"
    return label


def build_document(
    *,
    kind: str,
    title: str,
    period_from: date | None,
    period_to: date | None,
    materials: DeliverableMaterials,
    generated_at_text: str,
    summary: str | None = None,
) -> DeliverableDocument:
    """유형에 맞는 절을 골라 문서 구조를 만든다.

    유형별 규칙은 deliverable_service._count 의 표와 같아야 한다 — 세어서 보여준
    것과 담기는 것이 다르면 미리보기가 거짓이 된다.

    `summary` 는 LLM 이 만든 개요 문장이다 (DLV-002-1·DLV-002-2, "LLM 호출은 개요
    1회"). WEEKLY_REPORT·PROJECT_STATUS 에만 개요 절이 있으므로 그 유형에서만
    쓰인다. `None` 이면 — LLM 을 아직 붙이지 않았거나 호출이 실패한 경우 —
    SUMMARY_PLACEHOLDER 로 되돌아간다. **없는 문장을 지어내지 않는다.**
    개요를 만드는 곳은 서비스(deliverable_service)이고 여기는 받은 문장을 넣기만
    한다 — 구조 함수는 DB·LLM 을 모른다.
    """
    period = (
        f"{period_from.isoformat()} ~ {period_to.isoformat()}"
        if period_from and period_to
        else "기간 전체"
    )
    document = DeliverableDocument(
        title=title,
        meta=[f"대상 기간: {period}", f"만든 시각: {generated_at_text}"],
    )

    if kind in ("WEEKLY_REPORT", "PROJECT_STATUS"):
        document.sections.append(
            Section(title="개요", note=summary or SUMMARY_PLACEHOLDER)
        )
        document.sections.append(
            Section(
                title="문서",
                header=["파일명", "유형", "등록일"],
                rows=[
                    [clean(item.filename), clean(item.document_type),
                     day(_as_date(item.created_at))]
                    for item in materials.documents
                ],
                note="이 기간에 등록된 문서가 없습니다.",
            )
        )
        document.sections.append(
            Section(
                title="완료한 태스크",
                header=["제목", "담당", "완료일"],
                rows=[
                    [
                        clean(item.title),
                        clean(getattr(getattr(item, "assignee", None), "name", None)),
                        day(_as_date(item.completed_at)),
                    ]
                    for item in materials.completed_tasks
                ],
                note="이 기간에 완료한 태스크가 없습니다.",
            )
        )
        document.sections.append(
            _decision_section(materials.decisions, "이 기간의 결정사항이 없습니다.")
        )
        document.sections.append(
            Section(
                title="일정·기한",
                header=["제목", "종류", "시작", "종료"],
                rows=[
                    [clean(item.title), clean(item.kind), day(item.starts_on),
                     day(item.ends_on)]
                    for item in materials.schedule_items
                ],
                note="이 기간에 걸리는 일정이 없습니다.",
            )
        )
        document.sections.append(
            Section(
                title="금액",
                header=["항목", "수량", "단가", "금액"],
                rows=[
                    [
                        clean(item.item_name),
                        clean(_trim_number(item.quantity)),
                        money(item.unit_price),
                        money(item.amount),
                    ]
                    for item in materials.amount_items
                ],
                note="이 기간의 금액 항목이 없습니다.",
            )
        )
    elif kind == "DECISION_LOG":
        document.sections.append(
            _decision_section(
                materials.decisions, "기록된 결정사항이 없습니다.", show_status=True
            )
        )
    elif kind == "MEETING_AGENDA":
        document.sections.append(
            _decision_section(materials.decisions, "미결 상태인 결정사항이 없습니다.")
        )

    return document


def render_markdown(**kwargs: Any) -> str:
    """산출물 본문을 Markdown 으로. 인자는 build_document 와 같다."""
    return to_markdown(build_document(**kwargs))


def to_markdown(document: DeliverableDocument) -> str:
    lines: list[str] = [f"# {document.title}", ""]
    lines.extend(f"- {line}" for line in document.meta)
    lines.append("")

    for section in document.sections:
        lines.extend([f"## {section.title}", ""])
        if section.header and section.rows:
            lines.append("| " + " | ".join(_md_cell(v) for v in section.header) + " |")
            lines.append("|" + "|".join(["---"] * len(section.header)) + "|")
            lines.extend(
                "| " + " | ".join(_md_cell(v) for v in row) + " |"
                for row in section.rows
            )
        elif section.header:
            # 빈 표 대신 한 줄로 없다고 적는다.
            lines.append(section.note or "해당 자료가 없습니다.")
        else:
            # 문단. 개요처럼 표가 아닌 절이다. 기울임으로 본문과 구별한다.
            lines.append(f"_{section.note}_" if section.note else "")
        lines.append("")

    # 끝에 개수를 다시 적지 않는다. 표를 세면 되고, 두 곳에 적으면 어긋난다.
    return "\n".join(lines).rstrip() + "\n"


def _md_cell(value: str) -> str:
    """Markdown 표에서 `|` 는 칸을 가른다.

    지우지 않고 전각으로 바꾼다 — 지우면 값이 달라 보인다("A|B" -> "AB" 는 다른
    이름이 된다).
    """
    return value.replace("|", "｜")


def _decision_section(
    decisions: list[Any], empty: str, *, show_status: bool = False
) -> Section:
    header = ["안건", "상태", "결정일"] if show_status else ["안건", "결정일"]
    rows = []
    for item in decisions:
        row = [clean(item.title)]
        if show_status:
            row.append(clean(item.status))
        row.append(day(item.decided_on))
        rows.append(row)
    return Section(title="결정사항", header=header, rows=rows, note=empty)


def _as_date(value: Any) -> date | None:
    """datetime 이면 날짜만 꺼낸다. 보고서에 시각까지 넣지 않는다."""
    if value is None:
        return None
    return value.date() if hasattr(value, "date") else value


def _trim_number(value: Decimal | None) -> str | None:
    """수량의 뒤 0 을 지운다. Numeric(18,4) 라 6 이 6.0000 으로 온다."""
    if value is None:
        return None
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text
