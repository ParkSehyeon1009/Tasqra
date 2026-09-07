# =============================================================================
# 이 파일의 책임: 금액 현황·단가 선례·산출물 count/list가 실제 DB 쿼리에서 같은
#   문서별 유효 분석 스냅샷을 고르는지 회귀 검증한다.
# 다른 파일과의 관계: amount_repository.py의 공통 스냅샷 규칙을
#   deliverable_repository.py도 재사용한다. 서비스 mock이 아니라 두 Repository를
#   같은 SQLite 데이터에 연결해 쿼리 결과를 직접 비교한다.
# Spring 비교: @DataJpaTest로 여러 Repository의 공통 Specification 결과를 실제
#   인메모리 DB에서 검증하는 통합 테스트에 해당한다.
# =============================================================================

import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.amount import AmountItem
from app.models.document import Analysis, Document
from app.models.project import Project
from app.repositories.amount_repository import AmountRepository
from app.repositories.deliverable_repository import DeliverableRepository


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):
    return "JSON"


def _register_jsonb_array_length(dbapi_connection, connection_record) -> None:
    """운영 PostgreSQL의 jsonb_array_length를 SQLite 테스트에 맞춘다."""
    def array_length(value):
        if value is None:
            return None
        parsed = json.loads(value) if isinstance(value, str) else value
        return len(parsed)

    dbapi_connection.create_function("jsonb_array_length", 1, array_length)


@pytest.fixture
def db():
    """운영 테이블 모양으로 쿼리하되 NULL analysis_id 레거시도 재현한다.

    정식 스키마의 analysis_id는 처음부터 NOT NULL이다. 다만 배포 DB의 수동 적재나
    스키마 드리프트 행을 잃지 않는 호환 규칙도 잠그기 위해, 테스트 물리 테이블만
    CREATE TABLE AS로 제약 없는 사본으로 바꾼다. ORM 매핑과 Repository SQL은 실제
    AmountItem을 그대로 사용한다.
    """
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", _register_jsonb_array_length)
    for table in (
        Project.__table__,
        Document.__table__,
        Analysis.__table__,
        AmountItem.__table__,
    ):
        table.create(engine, checkfirst=True)

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE amount_items_legacy AS "
            "SELECT * FROM amount_items WHERE 0"
        )
        connection.exec_driver_sql("DROP TABLE amount_items")
        connection.exec_driver_sql(
            "ALTER TABLE amount_items_legacy RENAME TO amount_items"
        )

    session = sessionmaker(bind=engine)()
    yield session
    session.close()


_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def 프로젝트(db, project_id: int, name: str) -> None:
    db.add(
        Project(
            id=project_id,
            name=name,
            owner_id=1,
            status="ACTIVE",
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def 문서(db, document_id: int, project_id: int, filename: str) -> None:
    db.add(
        Document(
            id=document_id,
            project_id=project_id,
            filename=filename,
            storage_path=f"/{filename}",
            file_type="PDF",
            file_size=1,
            status="COMPLETED",
            processing_mode="NORMAL",
            extraction_strategy="AUTO",
            review_status="NOT_REQUIRED",
            ocr_revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def 분석(
    db, analysis_id: int, document_id: int, *, extracted_item_count: int = 1
) -> None:
    db.add(
        Analysis(
            id=analysis_id,
            document_id=document_id,
            analyzer_type="amount",
            result_json={"items": [{} for _ in range(extracted_item_count)]},
            provider="test",
            model_name="test",
            source_text_revision=1,
            created_at=_NOW,
        )
    )


def 금액(
    db,
    item_id: int,
    document_id: int,
    analysis_id: int | None,
    decision: str,
    *,
    unit_price: str,
) -> AmountItem:
    row = AmountItem(
        id=item_id,
        document_id=document_id,
        analysis_id=analysis_id,
        item_name="특급기술자",
        quantity=Decimal("1"),
        unit="인월",
        unit_price=Decimal(unit_price),
        amount=Decimal(unit_price),
        currency="KRW",
        reason="test",
        decision=decision,
        source_text_revision=1,
        created_at=_NOW,
        updated_at=_NOW,
    )
    db.add(row)
    return row


def 소비처_ids(db, project_id: int) -> tuple[list[int], list[int], list[int], int]:
    amounts = AmountRepository(db)
    deliverables = DeliverableRepository(db)
    summary_ids = [row[0].id for row in amounts.list_project_items(project_id)]
    precedent_ids = [
        row[0].id
        for row in amounts.list_precedents(
            item_name="특급기술자", project_ids=[project_id], limit=200
        )
    ]
    list_ids = [row.id for row in deliverables.list_amount_items(project_id)]
    count = deliverables.count_amount_items(project_id)
    return summary_ids, precedent_ids, list_ids, count


def 모든_소비처가(db, project_id: int, expected_ids: set[int]) -> None:
    summary_ids, precedent_ids, list_ids, count = 소비처_ids(db, project_id)
    assert set(summary_ids) == expected_ids
    assert set(precedent_ids) == expected_ids
    assert set(list_ids) == expected_ids
    assert count == len(list_ids) == len(expected_ids)


def test_부분_검토_중에는_이전_완료_스냅샷을_유지하고_완료_후_전환한다(db):
    프로젝트(db, 1, "현재 사업")
    문서(db, 10, 1, "원가계산서.pdf")
    분석(db, 100, 10, extracted_item_count=2)
    금액(db, 1001, 10, 100, "APPROVED", unit_price="100")
    금액(db, 1002, 10, 100, "EDITED", unit_price="200")
    db.flush()

    # 분석 #1 전체 승인: 현황·선례·산출물 모두 #1만 사용한다.
    모든_소비처가(db, 1, {1001, 1002})

    분석(db, 200, 10, extracted_item_count=2)
    두번째_첫째 = 금액(db, 2001, 10, 200, "PENDING", unit_price="300")
    두번째_둘째 = 금액(db, 2002, 10, 200, "PENDING", unit_price="400")
    db.flush()

    # 분석 #2가 전부 PENDING이면 계속 #1을 사용한다.
    모든_소비처가(db, 1, {1001, 1002})

    # 일부만 승인해도 PENDING이 남아 있으므로 #1을 유지한다.
    두번째_첫째.decision = "APPROVED"
    db.flush()
    모든_소비처가(db, 1, {1001, 1002})

    # 마지막 항목까지 승인/수정/거절 중 하나가 되면 #2로 원자적으로 전환한다.
    두번째_둘째.decision = "REJECTED"
    db.flush()
    모든_소비처가(db, 1, {2001})


def test_실제_0행_추출은_승인_금액_0건인_완료_스냅샷으로_전환한다(db):
    프로젝트(db, 1, "현재 사업")
    문서(db, 10, 1, "빈-예산서.pdf")
    분석(db, 100, 10)
    금액(db, 1001, 10, 100, "APPROVED", unit_price="100")
    # AmountWriter가 저장하는 검증된 빈 결과. 검토할 항목이 없으므로 즉시 완료다.
    분석(db, 200, 10, extracted_item_count=0)
    db.flush()

    모든_소비처가(db, 1, set())


def test_재분석으로_pending이_삭제된_부분검토_과거분석은_완료로_오인하지_않는다(db):
    프로젝트(db, 1, "현재 사업")
    문서(db, 10, 1, "연속-재분석.pdf")
    분석(db, 100, 10)
    금액(db, 1001, 10, 100, "APPROVED", unit_price="100")

    분석(db, 200, 10, extracted_item_count=2)
    금액(db, 2001, 10, 200, "APPROVED", unit_price="200")
    금액(db, 2002, 10, 200, "PENDING", unit_price="201")
    db.flush()
    # 실제 AmountWriter가 다음 분석을 저장하기 직전에 수행하는 교체 동작이다.
    assert AmountRepository(db).delete_pending_items(10) == 1
    분석(db, 300, 10)
    금액(db, 3001, 10, 300, "PENDING", unit_price="300")
    db.flush()

    # #2의 승인 부분집합이 완료본으로 승격되면 여기서 {2001}로 바뀐다.
    모든_소비처가(db, 1, {1001})


def test_새_완료_스냅샷이_전부_거절이면_승인_금액은_0건이다(db):
    프로젝트(db, 1, "현재 사업")
    문서(db, 10, 1, "예산서.pdf")
    분석(db, 100, 10)
    금액(db, 1001, 10, 100, "APPROVED", unit_price="100")
    분석(db, 200, 10, extracted_item_count=2)
    금액(db, 2001, 10, 200, "REJECTED", unit_price="200")
    금액(db, 2002, 10, 200, "REJECTED", unit_price="300")
    db.flush()

    # 승인 행이 있는 과거 #1로 후퇴하면 안 된다.
    모든_소비처가(db, 1, set())


def test_문서마다_다른_유효_분석을_고르고_다른_프로젝트는_섞지_않는다(db):
    프로젝트(db, 1, "현재 사업")
    프로젝트(db, 2, "다른 사업")
    문서(db, 10, 1, "문서-A.pdf")
    문서(db, 20, 1, "문서-B.pdf")
    문서(db, 30, 2, "남의-문서.pdf")

    # 문서 A는 #2가 검토 중이라 #1 유지.
    분석(db, 101, 10)
    금액(db, 1011, 10, 101, "APPROVED", unit_price="101")
    분석(db, 102, 10)
    금액(db, 1021, 10, 102, "PENDING", unit_price="102")

    # 문서 B는 #2 검토가 끝나 #2로 전환. #1은 중복되면 안 된다.
    분석(db, 201, 20)
    금액(db, 2011, 20, 201, "APPROVED", unit_price="201")
    분석(db, 202, 20)
    금액(db, 2021, 20, 202, "APPROVED", unit_price="202")

    # 같은 항목명의 다른 프로젝트 금액.
    분석(db, 301, 30)
    금액(db, 3011, 30, 301, "APPROVED", unit_price="301")
    db.flush()

    모든_소비처가(db, 1, {1011, 2021})
    모든_소비처가(db, 2, {3011})


def test_analysis_id_없는_승인_레거시_행은_독립_수동_항목으로_보존한다(db):
    프로젝트(db, 1, "현재 사업")
    문서(db, 10, 1, "레거시.pdf")
    분석(db, 100, 10)
    금액(db, 1001, 10, 100, "APPROVED", unit_price="100")
    금액(db, 9001, 10, None, "APPROVED", unit_price="900")
    금액(db, 9002, 10, None, "PENDING", unit_price="901")
    db.flush()

    # NULL 분석 행은 분석 교체 대상이 아니며, 승인된 행만 모든 소비처에 보존한다.
    모든_소비처가(db, 1, {1001, 9001})
