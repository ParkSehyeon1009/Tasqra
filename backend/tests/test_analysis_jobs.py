import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.services.analysis_job_service import AnalysisJobService
from app.services.analysis_service import AnalysisService
from app.services.analysis_service import DEFAULT_ANALYZER_TYPES


def setup_job(status="PENDING", revision=3):
    now = datetime.now(timezone.utc)
    job = SimpleNamespace(id="job-1", project_id=1, document_id=2,
        source_text_revision=revision, analyzer_types=["summary", "category"], status=status,
        source_text_hash=hashlib.sha256("원문".encode("utf-8")).hexdigest(),
        stage="대기 중", completed_units=0, total_units=0, analysis_ids=[],
        error_code=None, error_message=None, analyzer_errors=[], created_at=now,
        expires_at=now + timedelta(minutes=10))
    document = SimpleNamespace(id=2, extracted_text=SimpleNamespace(content="원문", text_version=3))
    db, docs, jobs, analysis = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    docs.get_by_id_for_update.return_value = document
    jobs.get.return_value = job
    jobs.latest.return_value = job
    jobs.active.return_value = None
    jobs.results.return_value = []
    analysis.validate_types.side_effect = lambda types: types or ["summary", "category"]
    analysis.analyze_text_isolated = AsyncMock(return_value=([("summary", "result")], []))
    analysis.save_results.return_value = [SimpleNamespace(id=91), SimpleNamespace(id=92)]
    return AnalysisJobService(db, docs, jobs, analysis), job, document


def test_completed_job_is_idempotent():
    service, job, _ = setup_job("COMPLETED")
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    service.analysis.analyze_text_isolated.assert_not_called()
    service.analysis.save_results.assert_not_called()


def test_duplicate_delivery_does_not_restart_running_job():
    service, job, _ = setup_job("RUNNING")
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    service.analysis.analyze_text_isolated.assert_not_called()


def test_worker_saves_results_and_completion_together():
    service, job, _ = setup_job()
    progress = MagicMock()
    asyncio.run(service.run(1, 2, job.id, progress))
    service.analysis.analyze_text_isolated.assert_awaited_once_with(
        "원문", ["summary", "category"], progress)
    assert job.status == "COMPLETED"
    assert job.analysis_ids == [91, 92]
    assert service.db.commit.call_count == 2


def test_changed_source_before_worker_does_not_call_model():
    service, job, _ = setup_job(revision=2)
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    assert job.status == "FAILED"
    assert job.error_code == "ANALYSIS_SOURCE_CHANGED"
    service.analysis.analyze_text_isolated.assert_not_called()


def test_changed_source_during_analysis_does_not_save():
    service, job, document = setup_job()
    async def change(*args):
        document.extracted_text.text_version = 4
        return ([], [])
    service.analysis.analyze_text_isolated.side_effect = change
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    assert job.status == "FAILED"
    assert job.error_code == "ANALYSIS_SOURCE_CHANGED"
    service.analysis.save_results.assert_not_called()


def test_reextracted_text_with_same_version_is_also_rejected():
    service, job, document = setup_job()
    document.extracted_text.content = "재추출되어 달라진 원문"
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    assert job.error_code == "ANALYSIS_SOURCE_CHANGED"
    service.analysis.analyze_text_isolated.assert_not_called()


def test_failed_analyzer_saves_successful_results_as_partial():
    service, job, _ = setup_job()
    service.analysis.analyze_text_isolated.return_value = ([('summary', 'result')], [{
        'analyzer': 'decision', 'code': 'AI_INVALID_RESPONSE',
        'message': '결정사항 추출 2/5 실패',
    }])
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    assert job.status == "PARTIAL"
    assert job.analyzer_errors[0]["analyzer"] == "decision"
    service.analysis.save_results.assert_called_once()


def test_all_failed_analyzers_do_not_save_results():
    service, job, _ = setup_job()
    service.analysis.analyze_text_isolated.return_value = ([], [{
        'analyzer': 'decision', 'code': 'AI_INVALID_RESPONSE',
        'message': '결정사항 추출 2/5 실패',
    }])
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    assert job.status == "FAILED"
    assert "2/5" in job.error_message
    service.analysis.save_results.assert_not_called()


def test_timeout_and_lost_worker_are_reported_as_failure():
    service, job, _ = setup_job("RUNNING")
    job.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    response = service.get(1, 2, job.id)
    assert response.status == "FAILED"
    assert response.error_code == "AI_TIMEOUT"


def test_enqueue_returns_active_job_without_new_dispatch():
    service, job, _ = setup_job("RUNNING")
    service.jobs.active.return_value = job
    dispatch = MagicMock()
    response = service.enqueue(1, 2, ["summary", "category"], dispatch)
    assert response.job_id == job.id
    dispatch.assert_not_called()
    service.jobs.add.assert_not_called()


def test_different_analyzer_request_is_not_silently_replaced_by_active_job():
    service, job, _ = setup_job("RUNNING")
    service.jobs.active.return_value = job
    with pytest.raises(BusinessError) as exc:
        service.enqueue(1, 2, ["category"], MagicMock())
    assert exc.value.error_code is ErrorCode.ANALYSIS_IN_PROGRESS


def test_queue_failure_records_error_and_does_not_report_success():
    service, job, _ = setup_job()
    service.jobs.add.return_value = job
    dispatch = MagicMock(side_effect=RuntimeError("secret broker URL"))
    with pytest.raises(BusinessError) as exc:
        service.enqueue(1, 2, ["summary"], dispatch)
    assert exc.value.error_code is ErrorCode.ANALYSIS_QUEUE_ERROR
    assert job.status == "FAILED"
    assert "secret" not in job.error_message


def test_get_scopes_job_to_project_and_document():
    service, job, _ = setup_job()
    service.jobs.get.return_value = None
    with pytest.raises(BusinessError):
        service.get(99, 20, job.id)
    service.jobs.get.assert_called_once_with(99, 20, job.id, lock=True)


def test_expired_job_cannot_save_late_model_result():
    service, job, _ = setup_job()
    async def expire(*args):
        job.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        return ([], [])
    service.analysis.analyze_text_isolated.side_effect = expire
    asyncio.run(service.run(1, 2, job.id, MagicMock()))
    assert job.status == "FAILED"
    service.analysis.save_results.assert_not_called()


def test_analysis_service_serializes_calls_and_validates_before_any_call():
    first = SimpleNamespace(analyze=AsyncMock(return_value="summary"))
    second = SimpleNamespace(analyze=AsyncMock(return_value="category"))
    service = AnalysisService(MagicMock(), MagicMock(), MagicMock(),
        {"summary": first, "category": second}, MagicMock(), MagicMock())
    with pytest.raises(BusinessError):
        service.validate_types(["summary", "invalid"])
    first.analyze.assert_not_called()
    results = asyncio.run(service.analyze_text("원문", service.validate_types(["summary", "summary", "category"])))
    assert results == [("summary", "summary"), ("category", "category")]


def test_analysis_service_isolates_one_analyzer_failure():
    failed = SimpleNamespace(analyze=AsyncMock(side_effect=BusinessError(
        ErrorCode.AI_INVALID_RESPONSE, "결정사항 응답 형식 오류")))
    successful_result = SimpleNamespace(result={"schedule_items": [], "failed_groups": []})
    successful = SimpleNamespace(analyze=AsyncMock(return_value=successful_result))
    service = AnalysisService(MagicMock(), MagicMock(), MagicMock(),
        {"decision": failed, "schedule": successful}, MagicMock(), MagicMock())

    results, errors = asyncio.run(service.analyze_text_isolated(
        "원문", ["decision", "schedule"]))

    assert results == [("schedule", successful_result)]
    assert errors == [{"analyzer": "decision", "code": "AI_INVALID_RESPONSE",
        "message": "결정사항 응답 형식 오류"}]


def test_default_analysis_includes_decisions_and_schedule():
    assert DEFAULT_ANALYZER_TYPES == ["summary", "category", "decision", "schedule", "action_task"]


def test_save_routes_decision_and_schedule_fields_to_writer():
    repository = MagicMock()
    writer = MagicMock()
    decision_analysis = SimpleNamespace(id=31)
    schedule_analysis = SimpleNamespace(id=32)
    writer.write_decisions.return_value = (decision_analysis, [SimpleNamespace()])
    writer.write_schedule_items.return_value = (schedule_analysis, [SimpleNamespace()])
    service = AnalysisService(MagicMock(), MagicMock(), repository, {}, writer, MagicMock())
    document = SimpleNamespace(id=2, project_id=1, ocr_revision=11, document_type=None,
        document_type_source=None)
    metadata = dict(provider="local", model_name="task-model",
        prompt_version="v1", tokens_in=1, tokens_out=2, latency_ms=3)
    decision_result = SimpleNamespace(result={"decisions": [{
        "title": "승인 확정", "content": None, "status": "DECIDED",
        "decided_on": "2026-09-02", "confidence": 0.9, "reason": "원문 근거",
    }]}, **metadata)
    schedule_result = SimpleNamespace(result={"schedule_items": [{
        "title": "제출 마감", "kind": "DEADLINE", "starts_on": None,
        "ends_on": "2026-09-10", "confidence": 0.8, "reason": "원문 근거",
    }]}, **metadata)

    rows = service.save_results(document, 7, [
        ("decision", decision_result), ("schedule", schedule_result)])

    assert rows == [decision_analysis, schedule_analysis]
    repository.create.assert_not_called()
    decision = writer.write_decisions.call_args.kwargs["extractions"][0]
    schedule = writer.write_schedule_items.call_args.kwargs["extractions"][0]
    assert decision.decided_on.isoformat() == "2026-09-02"
    assert schedule.ends_on.isoformat() == "2026-09-10"
    assert writer.write_decisions.call_args.kwargs["project_id"] == 1
    assert writer.write_decisions.call_args.kwargs["source_ocr_revision"] == 11
    assert writer.write_schedule_items.call_args.kwargs["source_text_revision"] == 7
    assert writer.write_schedule_items.call_args.kwargs["source_ocr_revision"] == 11


def test_empty_suggestion_fields_still_use_writer_for_single_analysis_row():
    writer = MagicMock()
    analysis = SimpleNamespace(id=33)
    writer.write_schedule_items.return_value = (analysis, [])
    service = AnalysisService(MagicMock(), MagicMock(), MagicMock(), {}, writer, MagicMock())
    document = SimpleNamespace(id=2, project_id=1, ocr_revision=11, document_type=None,
        document_type_source=None)
    result = SimpleNamespace(result={"schedule_items": []}, provider="local",
        model_name="schedule-model", prompt_version="schedule-v1", tokens_in=1,
        tokens_out=2, latency_ms=3)

    assert service.save_results(document, 7, [("schedule", result)]) == [analysis]
    assert writer.write_schedule_items.call_args.kwargs["extractions"] == []


def test_invalid_suggestion_field_is_rejected_before_writer():
    writer = MagicMock()
    service = AnalysisService(MagicMock(), MagicMock(), MagicMock(), {}, writer, MagicMock())
    document = SimpleNamespace(id=2, project_id=1, document_type=None,
        document_type_source=None)
    result = SimpleNamespace(result={"schedule_items": [{
        "title": "잘못된 일정", "kind": "UNKNOWN", "starts_on": None,
        "ends_on": "2026-09-10", "confidence": 0.8, "reason": "원문 근거",
    }]}, provider="local", model_name="schedule-model",
        prompt_version="schedule-v1", tokens_in=1, tokens_out=2, latency_ms=3)

    with pytest.raises(BusinessError) as exc:
        service.save_results(document, 7, [("schedule", result)])

    assert exc.value.error_code == ErrorCode.AI_INVALID_RESPONSE
    writer.write_schedule_items.assert_not_called()


def test_save_uses_snapshot_version_not_current_ocr_revision():
    repository = MagicMock()
    repository.create.side_effect = lambda row: row
    service = AnalysisService(MagicMock(), MagicMock(), repository, {}, MagicMock(), MagicMock())
    result = SimpleNamespace(result={"category": "ETC"}, provider="fake", model_name="fake",
        prompt_version="category-v2", tokens_in=None, tokens_out=None, latency_ms=None)
    document = SimpleNamespace(id=2, document_type=None, document_type_source=None)
    rows = service.save_results(document, 7, [("category", result)])
    assert rows[0].source_text_revision == 7
    assert rows[0].result_json["category"] == "ETC"


def test_job_migration_builds_postgres_table_and_active_unique_index():
    import importlib.util
    import io
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import postgresql
    from app.models.analysis_job import AnalysisJob

    migration_dir = Path(__file__).parents[1] / "migrations/versions"
    path = migration_dir / "20260831_0023_analysis_jobs.py"
    partial_path = migration_dir / "20260903_0027_analysis_partial.py"
    spec = importlib.util.spec_from_file_location("analysis_job_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    partial_spec = importlib.util.spec_from_file_location("analysis_partial_migration", partial_path)
    partial_migration = importlib.util.module_from_spec(partial_spec)
    partial_spec.loader.exec_module(partial_migration)
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        migration.upgrade()
        partial_migration.upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE analysis_jobs" in sql
    assert "CREATE UNIQUE INDEX uq_analysis_job_active" in sql
    assert "WHERE status IN ('PENDING','RUNNING')" in sql
    assert "PARTIAL" in sql
    assert "analyzer_errors" in sql
    orm_sql = str(CreateTable(AnalysisJob.__table__).compile(dialect=postgresql.dialect()))
    for col in AnalysisJob.__table__.columns:
        assert col.name in sql
        assert col.name in orm_sql
