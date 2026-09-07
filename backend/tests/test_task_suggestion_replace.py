"""태스크 제안 테이블에 **분석기가 둘** 쓸 때의 교체 규칙.

🔴 이 파일이 생긴 이유 (2026-09-07):
   action_task 와 features 가 같은 테이블에 쓰게 되자, 한 번의 분석 안에서
   뒤에 도는 features 가 앞서 저장된 action_task 9건을 지웠다. 실측으로만
   드러났다 — 기존 테스트는 변환 함수와 건너뛰기 규칙만 보고 있었고
   **두 분석기가 순서대로 쓰는 상황을 재현하지 않았다.**

여기서 잠그는 것:
  ① 같은 분석기의 이전 미검토 후보는 교체된다 (재분석이 목록을 불리지 않는다)
  ② **다른 분석기의 후보는 건드리지 않는다**
  ③ 이미 검토한 것(APPROVED·REJECTED)은 어느 쪽이든 보존된다
  ④ analyzer_type 은 키워드 필수다 — 빠뜨리면 예전 동작으로 조용히 돌아간다
"""
import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.models.document import Analysis
from app.models.task_suggestion import TaskSuggestion
from app.repositories.task_suggestion_repository import TaskSuggestionRepository


# ⚠️ 이 저장소의 다른 테스트는 DB 를 띄우지 않고 메타데이터만 본다. 여기서는
#   **실제 쿼리로 재현해야** 의미가 있다 — 잡으려는 것이 「어떤 행이 지워지는가」
#   라는 동작이기 때문이다. 그래서 메모리 SQLite 를 쓴다.
#
#   두 가지를 맞춰줘야 한다:
#     · JSONB 는 SQLite 가 모른다 -> JSON 으로 렌더링
#     · 필요한 표만 만든다 -> 다른 표(deliverables 등)의 타입까지 끌고 오지 않는다
@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    for table in (Analysis.__table__, TaskSuggestion.__table__):
        table.create(engine, checkfirst=True)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


# SQLite 는 BigInteger 기본키를 자동으로 채우지 않는다(INTEGER PRIMARY KEY 만
# 자동 증가한다). 실제 DB 는 Postgres 라 문제가 안 되지만 여기서는 직접 준다.
_다음id = iter(range(1, 10_000))


def 분석(db, analyzer_type, document_id=1):
    row = Analysis(id=next(_다음id), document_id=document_id,
                   analyzer_type=analyzer_type, result_json={},
                   provider="t", model_name="t", source_text_revision=1)
    db.add(row)
    db.flush()
    return row


def 제안(db, analysis, title, decision="PENDING", document_id=1):
    row = TaskSuggestion(id=next(_다음id), project_id=1, document_id=document_id,
                         analysis_id=analysis.id, title=title,
                         evidence_text=title, evidence_fingerprint=title,
                         quality_score=0.5, reason="-", decision=decision,
                         source_text_revision=1)
    db.add(row)
    db.flush()
    return row


def 남은제목(db):
    return sorted(r.title for r in db.query(TaskSuggestion).all())


def test_같은_분석기의_미검토_후보는_교체된다(db):
    이전 = 분석(db, "action_task")
    제안(db, 이전, "옛 의무")
    TaskSuggestionRepository(db).delete_pending(1, 1, analyzer_type="action_task")
    assert 남은제목(db) == []


def test_다른_분석기의_후보는_건드리지_않는다(db):
    """🔑 실제로 났던 버그. features 가 저장하며 action_task 9건을 지웠다."""
    액션 = 분석(db, "action_task")
    제안(db, 액션, "월간 작업결과 보고")
    제안(db, 액션, "착수신고서 제출")
    과업 = 분석(db, "features")
    제안(db, 과업, "옛 과업")

    # features 가 자기 결과를 교체한다 — action_task 것은 남아야 한다.
    TaskSuggestionRepository(db).delete_pending(1, 1, analyzer_type="features")

    assert 남은제목(db) == ["월간 작업결과 보고", "착수신고서 제출"]


def test_검토한_것은_보존된다(db):
    액션 = 분석(db, "action_task")
    제안(db, 액션, "승인한 것", decision="APPROVED")
    제안(db, 액션, "거절한 것", decision="REJECTED")
    제안(db, 액션, "아직 안 본 것")

    TaskSuggestionRepository(db).delete_pending(1, 1, analyzer_type="action_task")

    assert 남은제목(db) == ["거절한 것", "승인한 것"]


def test_다른_문서는_건드리지_않는다(db):
    남의문서 = 분석(db, "features", document_id=2)
    제안(db, 남의문서, "남의 문서 과업", document_id=2)
    내문서 = 분석(db, "features", document_id=1)
    제안(db, 내문서, "내 문서 과업")

    TaskSuggestionRepository(db).delete_pending(1, 1, analyzer_type="features")

    assert 남은제목(db) == ["남의 문서 과업"]


def test_analyzer_type_은_키워드_필수다():
    """⚠️ 기본값을 두면 부르는 쪽이 빠뜨려도 조용히 「전부 삭제」로 돌아간다."""
    sig = inspect.signature(TaskSuggestionRepository.delete_pending)
    param = sig.parameters["analyzer_type"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty, "기본값이 있으면 안 된다"
