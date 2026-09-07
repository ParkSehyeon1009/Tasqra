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
# ⚠ 프로젝트 현황과 주간 보고서 요약은 DB 자료만으로 구성한다
#   프로젝트 현황의 기본정보·업무 완료율·성과·일정 이슈·향후 계획과 주간
#   보고서의 실적·결정·일정·금액은 서비스가 조회한 실제 값만 사용한다.
#   저장되지 않은 진행률·위험을 추정하거나 LLM 문장을 덧붙이지 않는다.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
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
NUMERIC_HEADERS = frozenset(
    {"수량", "단가", "금액", "건수", "전체 작업", "완료 작업", "업무 완료율", "기한 초과"}
)

# AI 분류와 사용자 수정이 저장하는 코드의 화면용 한국어 이름. 산출물은 서버에서
# HTML·Markdown·XLSX·PDF를 모두 만들므로 이 공통 구조에서 바꿔야 네 형식이 같다.
DOCUMENT_TYPE_LABELS = {
    "RFP": "제안요청서·입찰공고",
    "PROPOSAL": "제안서·기술제안서",
    "COST_SHEET": "산출내역서·견적서",
    "CONTRACT": "계약서·과업지시서",
    "CONTRACT_CHANGE": "변경계약서·과업변경합의서",
    "REPORT": "보고서·검사조서",
    "MEETING_NOTES": "회의록",
    "ETC": "기타 (세금계산서·대가지급청구서 포함)",
}


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

    # 프로젝트 현황(PROJECT_STATUS)의 구조화 개요 재료. 수치·날짜·대상 선별은
    # LLM이 아니라 리포지토리와 서비스가 확정한다.
    project: Any | None = None
    task_total: int = 0
    task_done: int = 0
    recent_completed_tasks: list[Any] = field(default_factory=list)
    overdue_tasks: list[Any] = field(default_factory=list)
    overdue_total: int = 0
    milestones: list[Any] = field(default_factory=list)
    upcoming_tasks: list[Any] = field(default_factory=list)
    upcoming_schedule_items: list[Any] = field(default_factory=list)
    status_as_of: date | None = None
    upcoming_from: date | None = None
    upcoming_until: date | None = None


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


def document_type_label(value: Any) -> str:
    """저장된 문서 유형 코드를 산출물용 한국어 이름으로 바꾼다.

    과거 BILLING은 현재 8종 계약의 ETC로 읽고, 새 코드가 생기면 숨기지 않고
    원값을 보여준다. 값이 없으면 대시 대신 의미가 분명한 '미분류'를 쓴다.
    """
    if value is None or value == "":
        return "미분류"
    code = getattr(value, "value", value)
    code = "ETC" if code in ("BILLING", "COST_SHEET") else str(code)
    return DOCUMENT_TYPE_LABELS.get(code, code)


def money(value: Decimal | int | None) -> str:
    """금액. 천 단위 구분을 넣는다. 없으면 — 다 (0 으로 바꾸지 않는다)."""
    if value is None:
        return EMPTY
    return f"{int(value):,}"


def day(value: date | None) -> str:
    return value.isoformat() if value else EMPTY


def schedule_moment(day_value, time_value=None, relative=None) -> str:
    if day_value:
        suffix = f" {time_value.strftime('%H:%M')}" if time_value else ""
        return f"{day_value.isoformat()}{suffix}"
    return clean(relative)


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

    `summary` 인자는 기존 렌더러 호출 계약을 위해 남아 있지만 더 이상 사용하지
    않는다. 주간 보고서와 프로젝트 현황 모두 DB에서 조회한 실제 자료로 구조화한다.
    """
    period = (
        f"{period_from.isoformat()} ~ {period_to.isoformat()}"
        if period_from and period_to
        else "기간 전체"
    )
    meta = [f"대상 기간: {period}", f"만든 시각: {generated_at_text}"]
    if kind == "PROJECT_STATUS":
        as_of = materials.status_as_of
        meta = [
            f"현황 기준일: {day(as_of)}",
            f"향후 계획 기간: {day(materials.upcoming_from)} ~ {day(materials.upcoming_until)}",
            f"만든 시각: {generated_at_text}",
        ]
    document = DeliverableDocument(title=title, meta=meta)

    if kind == "PROJECT_STATUS":
        document.sections.extend(
            _project_status_sections(materials, generated_at_text=generated_at_text)
        )
        _append_material_sections(document, materials, period_scoped=False)
    elif kind == "WEEKLY_REPORT":
        document.sections.append(_weekly_summary_section(materials))
        _append_material_sections(document, materials, period_scoped=True)
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


def _weekly_summary_section(materials: DeliverableMaterials) -> Section:
    """주간 변동을 실제 자료가 있는 항목만 모아 두 열로 요약한다.

    전체 진행률이나 정상·지연 같은 상태는 계획 기준선 없이는 판정할 수 없다.
    따라서 이 기간에 조회된 문서·완료 작업·승인 결정·승인 일정·승인 금액만
    압축하고, 제목은 두 건까지만 보여 준다.
    """
    rows: list[list[str]] = []

    achievement_parts: list[str] = []
    if materials.documents:
        achievement_parts.append(f"문서 {len(materials.documents)}건 등록")
    if materials.completed_tasks:
        achievement_parts.append(f"태스크 {len(materials.completed_tasks)}건 완료")
    if achievement_parts:
        rows.append(["실적", " · ".join(achievement_parts)])

    if materials.decisions:
        rows.append(
            ["결정", _limited_summary(materials.decisions, lambda item: clean(item.title))]
        )

    if materials.schedule_items:
        rows.append(
            [
                "일정",
                _limited_summary(
                    materials.schedule_items,
                    lambda item: f"{_schedule_period(item)} {clean(item.title)}",
                ),
            ]
        )

    if materials.amount_items:
        total = sum(int(item.amount or 0) for item in materials.amount_items)
        rows.append(
            [
                "금액",
                f"승인 금액 항목 {len(materials.amount_items)}건 · 단순 합계 {money(total)}원",
            ]
        )

    return Section(
        title="주간 요약",
        header=["구분", "내용"],
        rows=rows,
        note="이 기간에 반영된 승인 자료가 없습니다.",
    )


def _limited_summary(
    items: list[Any], formatter: Callable[[Any], str], *, limit: int = 2
) -> str:
    """대표 항목을 최대 두 건 표시하고 남은 건수는 숨기지 않는다."""
    values = [formatter(item) for item in items[:limit]]
    remaining = len(items) - limit
    if remaining > 0:
        values.append(f"외 {remaining}건")
    return " · ".join(values)


def _schedule_period(item: Any) -> str:
    """승인 일정의 시작·종료일을 한 칸에서 읽을 수 있게 표시한다."""
    starts_on = getattr(item, "starts_on", None)
    ends_on = getattr(item, "ends_on", None)
    if starts_on and ends_on and starts_on != ends_on:
        return f"{day(starts_on)}~{day(ends_on)}"
    return day(starts_on or ends_on)


def _project_status_sections(
    materials: DeliverableMaterials, *, generated_at_text: str
) -> list[Section]:
    """프로젝트 현황 상단의 다섯 절을 DB 값만으로 만든다.

    LLM은 전체 진행률·위험·마일스톤 달성을 추정할 근거가 없다. 업무 완료율은
    `DONE / 전체 태스크`, 일정 이슈는 `기한 경과 + 미완료`로만 계산하고, 저장되지
    않은 리스크 대응이나 마일스톤 달성 여부는 그대로 미관리라고 표시한다.
    """
    project = materials.project
    upcoming_from = materials.upcoming_from
    upcoming_until = materials.upcoming_until
    owner = getattr(getattr(project, "owner", None), "name", None)

    project_period = _project_period(project)
    basic = Section(
        title="프로젝트 기본 정보",
        header=["프로젝트명", "기간", "책임자", "작성일"],
        rows=[
            [
                clean(getattr(project, "name", None)),
                project_period,
                clean(owner),
                generated_at_text[:10],
            ]
        ],
    )

    completion_rate = "계산 불가"
    if materials.task_total > 0:
        raw_rate = materials.task_done * 100 / materials.task_total
        completion_rate = f"{raw_rate:.1f}".rstrip("0").rstrip(".") + "%"
    progress = Section(
        title="진행 상태 요약",
        header=["전체 작업", "완료 작업", "업무 완료율", "기한 초과"],
        rows=[
            [
                str(materials.task_total),
                str(materials.task_done),
                completion_rate,
                str(materials.overdue_total),
            ]
        ],
        note="태스크가 없어 업무 완료율을 계산할 수 없습니다.",
    )

    achievement_rows = [
        ["완료 작업", clean(item.title), day(_as_date(item.completed_at)), "완료"]
        for item in materials.recent_completed_tasks[:5]
    ]
    if len(materials.recent_completed_tasks) > 5:
        achievement_rows.append(
            ["안내", "최근 완료 작업 5건만 표시", EMPTY, EMPTY]
        )
    for item in materials.milestones[:5]:
        due = getattr(item, "due_on", None)
        achievement_rows.append(
            ["마일스톤", clean(item.title), day(due), "달성 여부 미관리"]
        )
    if len(materials.milestones) > 5:
        achievement_rows.append(
            ["안내", "최근 마일스톤 5건만 표시", EMPTY, EMPTY]
        )
    achievements = Section(
        title="주요 성과",
        header=["구분", "항목", "완료·예정일", "상태"],
        rows=achievement_rows,
        note="완료 작업과 승인된 마일스톤이 없습니다.",
    )

    issue_rows = [
        [clean(item.title), day(item.due_on)]
        for item in materials.overdue_tasks[:5]
    ]
    if materials.overdue_total > 5:
        issue_rows.append(
            [
                f"기한 초과 {materials.overdue_total}건 중 5건만 표시",
                EMPTY,
            ]
        )
    issues = Section(
        title="일정 이슈",
        header=["내용", "기한"],
        rows=issue_rows,
        note="기한이 지난 미완료 작업이 없습니다.",
    )

    plan_rows = [
        [
            "미완료 작업",
            clean(item.title),
            day(item.due_on),
            _task_status_label(item.status),
        ]
        for item in materials.upcoming_tasks[:5]
    ]
    if len(materials.upcoming_tasks) > 5:
        plan_rows.append(["안내", "예정 작업 5건만 표시", EMPTY, EMPTY])
    plan_rows.extend(
        [
            "승인 일정",
            clean(item.title),
            day(getattr(item, "due_on", None)),
            _schedule_kind_label(item.kind),
        ]
        for item in materials.upcoming_schedule_items[:5]
    )
    if len(materials.upcoming_schedule_items) > 5:
        plan_rows.append(["안내", "승인 일정 5건만 표시", EMPTY, EMPTY])
    plan_period = (
        f"{day(upcoming_from)} ~ {day(upcoming_until)}"
        if upcoming_from and upcoming_until
        else "향후 7일"
    )
    future_plan = Section(
        title="향후 계획",
        header=["구분", "항목", "예정일", "상태"],
        rows=plan_rows,
        note=f"{plan_period}에 예정된 미완료 작업이나 승인 일정이 없습니다.",
    )
    return [basic, progress, achievements, issues, future_plan]


def _append_material_sections(
    document: DeliverableDocument,
    materials: DeliverableMaterials,
    *,
    period_scoped: bool,
) -> None:
    """다섯 종류의 실제 자료 표를 주간 보고서와 프로젝트 현황에 공통으로 붙인다."""
    scope = "이 기간에" if period_scoped else "현재"
    document.sections.append(
        Section(
            title="문서",
            header=["파일명", "유형", "등록일"],
            rows=[
                [
                    clean(item.filename),
                    document_type_label(item.document_type),
                    day(_as_date(item.created_at)),
                ]
                for item in materials.documents
            ],
            note=f"{scope} 등록된 문서가 없습니다.",
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
            note=f"{scope} 완료한 태스크가 없습니다.",
        )
    )
    document.sections.append(
        _decision_section(materials.decisions, f"{scope} 결정사항이 없습니다.")
    )
    document.sections.append(
        Section(
            title="일정·기한",
            header=["제목", "종류", "시작", "종료"],
            # ⚠️ day() 가 아니라 schedule_moment() 다. 날짜만 찍으면 「9월 1일
            #   10:00 마감」이 「9월 1일」이 되어 **몇 시까지인지 사라진다.**
            #   상대 기한(「계약일로부터 30일 이내」)도 마찬가지다.
            #
            #   상대 표현은 종류에 따라 붙는 쪽이 다르다 — DEADLINE 은 끝에,
            #   나머지는 시작에 건다. 「계약일로부터 30일 이내」는 마감이고,
            #   「착수일로부터 6개월」은 시작 기준이기 때문이다.
            rows=[
                [
                    clean(item.title),
                    _schedule_kind_label(item.kind),
                    schedule_moment(
                        item.starts_on,
                        getattr(item, "starts_time", None),
                        getattr(item, "relative_expression", None)
                        if item.kind != "DEADLINE" else None,
                    ),
                    schedule_moment(
                        item.ends_on,
                        getattr(item, "ends_time", None),
                        getattr(item, "relative_expression", None)
                        if item.kind == "DEADLINE" else None,
                    ),
                ]
                for item in materials.schedule_items
            ],
            note=f"{scope} 일정이 없습니다.",
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
            note=f"{scope} 금액 항목이 없습니다.",
        )
    )


def _project_period(project: Any | None) -> str:
    if project is None:
        return EMPTY
    started = day(getattr(project, "started_on", None))
    due = day(getattr(project, "due_on", None))
    if started == EMPTY and due == EMPTY:
        return EMPTY
    return f"{started} ~ {due}"


def _task_status_label(status: Any) -> str:
    return {
        "TODO": "할 일",
        "IN_PROGRESS": "진행 중",
        "DONE": "완료",
    }.get(str(status), clean(status))


def _schedule_kind_label(kind: Any) -> str:
    return {
        "MILESTONE": "마일스톤",
        "DEADLINE": "기한",
        "MEETING": "회의",
        "PERIOD": "기간",
    }.get(str(kind), clean(kind))


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
