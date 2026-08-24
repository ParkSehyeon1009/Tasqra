# =============================================================================
# 이 파일의 책임: 산출물 본문을 Markdown 문자열로 만든다. DB·파일·HTTP 를 모르고
#   받은 자료만 문자열로 바꾼다.
#
# 다른 파일과의 관계
#   services/deliverable_service.py  자료를 모아 이 함수를 부르고 파일로 저장한다
#   repositories/deliverable_repository.py  자료를 조회한다
#   schemas/deliverable.py  유형 이름(DELIVERABLE_KIND_LABELS)을 여기서도 쓴다
#
# Spring 비교: 템플릿 엔진(Thymeleaf·Freemarker) 자리다. 다만 템플릿 파일을 두지
#   않고 문자열을 직접 만든다 — 표 몇 개라 템플릿 문법을 더할 이유가 없고,
#   순수 함수라 DB 없이 테스트된다.
#
# ⚠ Markdown 을 먼저 만드는 이유
#   새 의존성이 없다. XLSX 는 openpyxl, PDF 는 폰트나 별도 라이브러리가 필요하고
#   그것은 팀 이미지 크기에 영향을 준다(이미 11.1GB 다). 형식을 늘리는 판단을
#   미뤄도 "만들기" 자체는 끝낼 수 있다.
#
# ⚠ 개요는 비어 있다 — 일부러 그렇다
#   DLV-002-1 완료 판정에 "LLM 호출은 개요 1회" 가 있다. 아직 LLM 이 붙지 않아
#   개요 문장을 만들 수 없다. **없는 문장을 지어내지 않고** 자리를 비워 두고
#   비었다고 적는다. 표는 전부 실제 자료다.
#
# ⚠ 표에 들어가는 값은 반드시 escape 한다
#   문서 이름이나 항목명에 `|` 가 있으면 표가 깨진다. 줄바꿈이 있으면 행이
#   갈라진다. 사용자 자료라 언제든 들어올 수 있다.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas.deliverable import DELIVERABLE_KIND_LABELS

__all__ = ["DeliverableMaterials", "build_title", "render_markdown"]

# 값이 없을 때 표에 넣는 글자. 0 과 구별한다.
EMPTY = "—"


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


def cell(value: Any) -> str:
    """표 한 칸에 넣을 문자열. None 은 —, 표를 깨뜨리는 글자는 바꾼다."""
    if value is None or value == "":
        return EMPTY
    text = str(value)
    # 줄바꿈은 공백으로, 파이프는 전각으로. 전각으로 바꾸는 이유는 지우면 값이
    # 달라 보이기 때문이다(예: "A|B" -> "AB" 는 다른 이름이 된다).
    return text.replace("\r", " ").replace("\n", " ").replace("|", "｜").strip()


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


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def _section(title: str, header: list[str], rows: list[list[str]], empty: str) -> list[str]:
    """제목 + 표. 행이 없으면 표 대신 한 줄로 없다고 적는다.

    빈 표를 넣지 않는 이유: 머리글만 있는 표는 "자료를 못 가져온 것" 처럼 보인다.
    """
    lines = [f"## {title}", ""]
    if rows:
        lines.extend(_table(header, rows))
    else:
        lines.append(empty)
    lines.append("")
    return lines


def render_markdown(
    *,
    kind: str,
    title: str,
    period_from: date | None,
    period_to: date | None,
    materials: DeliverableMaterials,
    generated_at_text: str,
) -> str:
    """산출물 본문. 유형에 따라 담는 절이 다르다.

    유형별 규칙은 deliverable_service._count 의 표와 같아야 한다 — 세어서 보여준
    것과 담기는 것이 다르면 미리보기가 거짓이 된다.
    """
    lines: list[str] = [f"# {title}", ""]

    period = (
        f"{period_from.isoformat()} ~ {period_to.isoformat()}"
        if period_from and period_to
        else "기간 전체"
    )
    lines.extend(
        [
            f"- 대상 기간: {period}",
            f"- 만든 시각: {generated_at_text}",
            "",
        ]
    )

    if kind in ("WEEKLY_REPORT", "PROJECT_STATUS"):
        lines.extend(
            [
                "## 개요",
                "",
                "_개요 문장은 아직 넣지 않았습니다. 저장된 문서 요약을 한 번 재요약해"
                " 채울 자리입니다(LLM 연결 예정). 아래 표는 모두 실제 자료입니다._",
                "",
            ]
        )
        lines.extend(
            _section(
                "문서",
                ["파일명", "유형", "등록일"],
                [
                    [cell(item.filename), cell(item.document_type), day(_as_date(item.created_at))]
                    for item in materials.documents
                ],
                "이 기간에 등록된 문서가 없습니다.",
            )
        )
        lines.extend(
            _section(
                "완료한 태스크",
                ["제목", "담당", "완료일"],
                [
                    [
                        cell(item.title),
                        cell(getattr(getattr(item, "assignee", None), "name", None)),
                        day(_as_date(item.completed_at)),
                    ]
                    for item in materials.completed_tasks
                ],
                "이 기간에 완료한 태스크가 없습니다.",
            )
        )
        lines.extend(_decision_section(materials.decisions, "이 기간의 결정사항이 없습니다."))
        lines.extend(
            _section(
                "일정·기한",
                ["제목", "종류", "시작", "종료"],
                [
                    [cell(item.title), cell(item.kind), day(item.starts_on), day(item.ends_on)]
                    for item in materials.schedule_items
                ],
                "이 기간에 걸리는 일정이 없습니다.",
            )
        )
        lines.extend(
            _section(
                "금액",
                ["항목", "수량", "단가", "금액"],
                [
                    [
                        cell(item.item_name),
                        cell(_trim_number(item.quantity)),
                        money(item.unit_price),
                        money(item.amount),
                    ]
                    for item in materials.amount_items
                ],
                "이 기간의 금액 항목이 없습니다.",
            )
        )
    elif kind == "DECISION_LOG":
        lines.extend(
            _decision_section(materials.decisions, "기록된 결정사항이 없습니다.", show_status=True)
        )
    elif kind == "MEETING_AGENDA":
        lines.extend(
            _decision_section(materials.decisions, "미결 상태인 결정사항이 없습니다.")
        )

    # 끝에 개수를 다시 적지 않는다. 표를 세면 되고, 두 곳에 적으면 어긋난다.
    return "\n".join(lines).rstrip() + "\n"


def _decision_section(
    decisions: list[Any], empty: str, *, show_status: bool = False
) -> list[str]:
    header = ["안건", "상태", "결정일"] if show_status else ["안건", "결정일"]
    rows = []
    for item in decisions:
        row = [cell(item.title)]
        if show_status:
            row.append(cell(item.status))
        row.append(day(item.decided_on))
        rows.append(row)
    return _section("결정사항", header, rows, empty)


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
