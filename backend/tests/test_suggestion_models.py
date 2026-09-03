# =============================================================================
# 이 파일의 책임: 리비전 0007이 만든 테이블과 리비전 0021이 확장한 산출물
#   형식을 ORM 매핑과 대조한다 — decisions · schedule_items · deliverables.
#
#   테이블 구조는 0007에 있고 산출물 형식의 최신 CHECK는 0021에 있다. 그래서
#   가장 큰 위험은 "컬럼 이름이 하나 틀렸다" 또는 "최신 CHECK 값이 모델과
#   달라 Alembic이 매번 제약을 다시 만든다"는 것이다.
#
#   검사하는 것
#     ① 마이그레이션의 컬럼 이름·개수와 모델이 같은가
#     ② CHECK·인덱스 이름이 마이그레이션과 같은가
#     ③ 값 목록(kind·status·decision)이 마이그레이션과 같은가
#     ④ 헬퍼(due_on · stale_against · is_open)의 판단이 맞는가
#
# 다른 파일과의 관계
#   app/models/decision.py · schedule.py · deliverable.py
#   migrations/versions/20260811_0007_analysis_artifacts.py  ← 테이블 생성 근거
#   migrations/versions/20260824_0021_deliverable_pdf_format.py
#     ← 산출물 출력 형식의 최신 근거
#
#   **마이그레이션 파일을 읽어서 비교한다.** 기대값을 손으로 적으면 여러 곳을
#   고쳐야 하고, 한쪽만 고치면 테스트가 거짓으로 통과한다.
#
# Spring 비교: @Entity 와 Flyway 스크립트가 어긋나지 않는지 보는 검사다.
#   Hibernate 의 hbm2ddl validate 가 하는 일을 DB 없이 소스 대조로 한다.
# =============================================================================

import ast
import re
from pathlib import Path

from app.models.decision import Decision
from app.models.deliverable import Deliverable
from app.models.schedule import ScheduleItem

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20260811_0007_analysis_artifacts.py"
)
FORMAT_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20260824_0021_deliverable_pdf_format.py"
)

# 리비전 0007 의 suggestion_columns() · timestamps() 가 더하는 컬럼.
# 마이그레이션이 함수로 펼치므로 정규식으로는 안 잡힌다.
_SUGGESTION = ("confidence", "reason", "decision", "decided_by",
               "decided_at", "source_text_revision")
_TIMESTAMPS = ("created_at", "updated_at")


def migration_block(table: str) -> str:
    """마이그레이션에서 그 테이블의 create_table 블록만 잘라낸다."""
    text = MIGRATION.read_text(encoding="utf-8")
    match = re.search(rf'op\.create_table\(\s*\n?\s*"{table}"', text)
    assert match, f"{table} 의 create_table 을 못 찾았다"
    start = text.index("(", match.start())
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[match.start() : i + 1]
    raise AssertionError("괄호 균형이 맞지 않는다")


def migration_columns(table: str) -> set[str]:
    block = migration_block(table)
    cols = set(re.findall(r'sa\.Column\(\s*"(\w+)"', block))
    if "*suggestion_columns()" in block:
        cols |= set(_SUGGESTION)
    if "*timestamps()" in block:
        cols |= set(_TIMESTAMPS)
    return cols


def model_columns(model) -> set[str]:
    return {c.name for c in model.__table__.columns}


# --- ① 컬럼이 마이그레이션과 같다 -------------------------------------------


def test_decision_columns_match_migration():
    assert model_columns(Decision) == migration_columns("decisions") | {"evidence_text"}


def test_schedule_columns_match_migration():
    assert model_columns(ScheduleItem) == migration_columns("schedule_items") | {
        "evidence_text", "starts_time", "ends_time", "relative_expression"}


def test_deliverable_columns_match_migration():
    assert model_columns(Deliverable) == migration_columns("deliverables")


def test_table_names():
    assert Decision.__tablename__ == "decisions"
    assert ScheduleItem.__tablename__ == "schedule_items"
    assert Deliverable.__tablename__ == "deliverables"


# --- ② CHECK·인덱스 이름이 마이그레이션과 같다 ------------------------------


def constraint_names(model) -> set[str]:
    return {c.name for c in model.__table__.constraints if c.name}


def index_names(model) -> set[str]:
    return {i.name for i in model.__table__.indexes}


def test_check_names_exist_in_migration():
    """CHECK 이름이 다르면 Alembic 이 지우고 다시 만드는 마이그레이션을 낸다."""
    text = MIGRATION.read_text(encoding="utf-8")
    for model in (Decision, ScheduleItem, Deliverable):
        for name in constraint_names(model):
            if name.startswith("ck_"):
                assert f'"{name}"' in text or f"'{name}'" in text, (
                    f"{name} 이 마이그레이션에 없다"
                )


def test_index_names_match_migration():
    text = MIGRATION.read_text(encoding="utf-8")
    expected = {
        Decision: {"ix_decision_project", "ix_decision_status",
                   "ix_decision_doc", "ix_decision_open"},
        ScheduleItem: {"ix_schedule_project", "ix_schedule_due", "ix_schedule_doc"},
        Deliverable: {"ix_deliverable_recent", "ix_deliverable_period"},
    }
    for model, names in expected.items():
        assert index_names(model) == names, model.__tablename__
        for name in names:
            assert f'"{name}"' in text, f"{name} 이 마이그레이션에 없다"


def test_partial_index_on_open_decisions():
    """미결 안건 조회용 부분 인덱스. 다음 회의 안건(DLV-003-2)이 쓴다."""
    index = next(i for i in Decision.__table__.indexes
                 if i.name == "ix_decision_open")
    where = index.dialect_options["postgresql"].get("where")
    assert where is not None, "부분 인덱스 조건이 없다"
    assert "PENDING" in str(where)


# --- ③ 값 목록이 마이그레이션과 같다 ----------------------------------------


def migration_assignment(name: str, source: Path = MIGRATION):
    """지정한 마이그레이션 상단의 상수 값을 읽는다."""
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} 을 못 찾았다")


def migration_tuple(name: str, source: Path = MIGRATION) -> tuple[str, ...]:
    """지정한 마이그레이션 상단의 값 목록 상수를 읽는다."""
    value = migration_assignment(name, source)
    assert isinstance(value, tuple), f"{name} 이 tuple 이 아니다"
    return tuple(value)


def check_values(model, constraint: str) -> set[str]:
    """CHECK 문구에서 'A', 'B' 형태의 값을 뽑는다."""
    target = next(c for c in model.__table__.constraints if c.name == constraint)
    return set(re.findall(r"'(\w+)'", str(target.sqltext)))


def test_decision_status_values():
    assert check_values(Decision, "ck_decision_status") == set(
        migration_tuple("DECISION_STATUS")
    )


def test_suggestion_decision_values_are_same_everywhere():
    """세 테이블이 같은 승인 상태 값을 써야 한다. 하나만 달라지면 안 된다."""
    expected = set(migration_tuple("SUGGESTION_DECISION"))
    assert check_values(Decision, "ck_decision_decision") == expected
    assert check_values(ScheduleItem, "ck_schedule_decision") == expected


def test_schedule_kind_values():
    assert check_values(ScheduleItem, "ck_schedule_kind") == set(
        migration_tuple("SCHEDULE_KIND")
    )


def test_deliverable_kind_and_format_values():
    assert check_values(Deliverable, "ck_deliverable_kind") == set(
        migration_tuple("DELIVERABLE_KIND")
    )
    assert check_values(Deliverable, "ck_deliverable_format") == set(
        migration_tuple("DELIVERABLE_FORMAT", FORMAT_MIGRATION)
    )


def test_deliverable_format_migration_follows_tasks_and_preserves_old_values():
    """0021은 액션 태스크 활동 기록 0020 뒤에 오고, 기존 3종을 보존한다."""
    assert migration_assignment("down_revision", FORMAT_MIGRATION) == "20260824_0020"
    assert migration_tuple(
        "PREVIOUS_DELIVERABLE_FORMAT", FORMAT_MIGRATION
    ) == migration_tuple("DELIVERABLE_FORMAT")


# --- ④ 헬퍼의 판단 ----------------------------------------------------------


def test_decision_is_open_means_status_not_approval():
    """status 와 decision 은 다른 것이다. 둘 다 PENDING 값을 가져 헷갈린다."""
    open_but_approved = Decision(status="PENDING", decision="APPROVED")
    assert open_but_approved.is_open is True
    assert open_but_approved.is_pending_approval is False

    decided_but_unapproved = Decision(status="DECIDED", decision="PENDING")
    assert decided_but_unapproved.is_open is False
    assert decided_but_unapproved.is_pending_approval is True


def test_schedule_due_on_depends_on_kind():
    from datetime import date

    start, end = date(2026, 3, 5), date(2026, 3, 19)
    # 한 시점인 것은 starts_on 이 기한이다.
    assert ScheduleItem(kind="MEETING", starts_on=start, ends_on=None).due_on == start
    assert ScheduleItem(kind="MILESTONE", starts_on=start, ends_on=None).due_on == start
    # 기한·구간은 ends_on 이 기한이다.
    assert ScheduleItem(kind="DEADLINE", starts_on=None, ends_on=end).due_on == end
    assert ScheduleItem(kind="PERIOD", starts_on=start, ends_on=end).due_on == end


def test_schedule_due_on_falls_back_when_end_missing():
    """DEADLINE 인데 ends_on 이 NULL 인 행이 있을 수 있다 — 문서에 없으면 NULL 이다."""
    from datetime import date

    start = date(2026, 3, 5)
    assert ScheduleItem(kind="DEADLINE", starts_on=start, ends_on=None).due_on == start
    assert ScheduleItem(kind="DEADLINE", starts_on=None, ends_on=None).due_on is None


def test_deliverable_needs_period_only_for_weekly_report():
    """DB CHECK 와 같은 판단이어야 한다."""
    assert Deliverable(kind="WEEKLY_REPORT").needs_period is True
    for kind in ("DECISION_LOG", "MEETING_AGENDA", "PROJECT_STATUS"):
        assert Deliverable(kind=kind).needs_period is False


def test_stale_against_reports_only_growth():
    """늘어난 것만 담는다. 줄어든 것으로 '갱신 필요' 를 띄우면 이유를 알 수 없다."""
    made = Deliverable(source_counts_json={"documents": 12, "decisions": 5, "tasks": 8})

    grown = made.stale_against({"documents": 15, "decisions": 6, "tasks": 8})
    assert grown == {"documents": 3, "decisions": 1}

    # 같으면 갱신이 필요 없다.
    assert made.stale_against({"documents": 12, "decisions": 5, "tasks": 8}) == {}
    # 줄어든 것은 담지 않는다.
    assert made.stale_against({"documents": 9, "decisions": 5, "tasks": 8}) == {}


def test_stale_against_treats_new_key_as_growth():
    """재료 종류가 나중에 추가되면 그 값 전부가 늘어난 것이다."""
    made = Deliverable(source_counts_json={"documents": 12})
    assert made.stale_against({"documents": 12, "amounts": 4}) == {"amounts": 4}


def test_stale_against_handles_missing_snapshot():
    """source_counts_json 이 비어 있어도 터지지 않아야 한다."""
    assert Deliverable(source_counts_json={}).stale_against({"documents": 3}) == {
        "documents": 3
    }
