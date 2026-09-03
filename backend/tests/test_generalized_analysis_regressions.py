import asyncio
import json
from types import SimpleNamespace

from app.ai.client_protocol import AIResult
from app.analyzers.action_candidate_finder import find_action_candidates
from app.analyzers.action_task_analyzer import ActionTaskAnalyzer
from app.analyzers.category_analyzer import _document_family, _document_state, _document_traits
from app.analyzers.date_finder import find_dates
from app.analyzers.schedule_analyzer import ScheduleAnalyzer
from app.analyzers.summary_analyzer import normalize_summary
from app.analyzers.prompts import (
    ACTION_TASK_PROMPT_VERSION,
    CATEGORY_PROMPT_VERSION,
    DECISION_PROMPT_VERSION,
    OVERVIEW_PROMPT_VERSION,
    SCHEDULE_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION,
)


class ScriptedAI:
    provider = "test"
    model_name = "test"

    def __init__(self, answer):
        self.answer = answer

    async def generate_with_meta(self, prompt):
        value = self.answer(prompt)
        return AIResult(text=json.dumps(value, ensure_ascii=False), model_name="test",
                        tokens_in=10, tokens_out=5)


CONFIG = SimpleNamespace(
    AI_CONTEXT_TOKENS=8192, AI_MAX_OUTPUT_TOKENS=1536,
    AI_MAX_INPUT_CHARS=2000, AI_CHUNK_OVERLAP_CHARS=60,
    AI_MAX_CHUNKS=256, AI_CHUNK_RETRIES=0, AI_TIMEOUT_SECONDS=5,
)


def test_persisted_prompt_versions_use_short_numeric_suffix():
    versions = (
        SUMMARY_PROMPT_VERSION, CATEGORY_PROMPT_VERSION, OVERVIEW_PROMPT_VERSION,
        DECISION_PROMPT_VERSION, SCHEDULE_PROMPT_VERSION, ACTION_TASK_PROMPT_VERSION,
    )
    assert all(len(version) <= 20 for version in versions)
    assert all(__import__("re").fullmatch(r"[a-z-]+-v\d+", version) for version in versions)


def test_appendix_example_date_is_not_saved_as_schedule():
    text = "접수마감: 2026. 8. 31. 18:00\n[별지 제1호 서식]\n참여일시 2020.11.5 12:30"
    found = find_dates(text)
    assert found[0].context_type == "body"
    assert found[1].context_type == "form_or_appendix"

    client = ScriptedAI(lambda _: {"items": [
        {"date_ids": ["d1"], "title": "접수마감", "kind": "DEADLINE",
         "confidence": 0.9, "reason": "본문의 마감"},
        {"date_ids": ["d2"], "title": "제출 마감", "kind": "DEADLINE",
         "confidence": 0.9, "reason": "서식 날짜"},
    ]})
    result = asyncio.run(ScheduleAnalyzer(client, CONFIG).analyze(text))
    assert [item["ends_on"] for item in result.result["schedule_items"]] == ["2026-08-31"]


def test_range_end_does_not_inherit_start_label():
    found = find_dates("제출시작일시: 2026/07/13 10:00 ~ 2026/07/15 10:00")
    assert found[0].label == "제출시작일시"
    assert found[1].label is None


def test_relative_duration_and_clean_deadline_title_are_preserved():
    text = ("기술제안서의 작성기간은 현장설명일로부터 70일로 한다. "
            "상품에 하자가 있는 경우에는 상품공급 후 30일 이내 교환한다.")
    client = ScriptedAI(lambda _: {"items": []})
    result = asyncio.run(ScheduleAnalyzer(client, CONFIG).analyze(text))
    items = result.result["schedule_items"]
    assert any(item["kind"] == "PERIOD" and "70일" in item["relative_expression"] for item in items)
    deadline = next(item for item in items if item["kind"] == "DEADLINE")
    assert deadline["title"] == "상품공급 후 기한"


def test_schedule_heading_is_not_action_task():
    candidates = find_action_candidates("납품기한: 2026/12/10\n낙찰자는 결과물을 납품하여야 한다.")
    assert all(not item.title.startswith("납품기한") for item in candidates)
    assert any("납품" in item.title for item in candidates)


def test_semantically_duplicate_submission_tasks_are_merged():
    text = ("제안서 및 증빙서류를 나라장터를 통해 제출하여야 한다.\n"
            "입찰자는 제안서를 국가종합전자조달시스템(나라장터)로 제출해야 한다.")
    client = ScriptedAI(lambda prompt: {
        "selected_ids": [record["id"] for record in json.loads(prompt.user)["candidates"]]
    })
    result = asyncio.run(ActionTaskAnalyzer(client, CONFIG).analyze(text))
    assert len(result.result["task_suggestions"]) == 1


def test_incomplete_summary_tail_is_removed_and_reported():
    summary, warnings = normalize_summary(
        "계약의 목적을 설명한다. 을이 이행하지 않을 경우 손해에 대한")
    assert summary == "계약의 목적을 설명한다."
    assert "incomplete_tail_removed" in warnings


def test_detailed_document_profile_distinguishes_role_state_and_traits():
    text = "제안요청서\n계약일로부터 10일 이내 결과물을 제출하여야 한다. 평가기준과 배점"
    assert _document_family(text) == "RFP"
    assert _document_state(text) == "PUBLISHED"
    assert {"EVALUATION_RULES", "RELATIVE_DEADLINES"} <= set(_document_traits(text))


def test_unadopted_proposal_commitment_is_not_created_as_project_task():
    text = "상품제안서\n제안사는 향후 제품을 제작하여 납품할 예정입니다."
    candidates = find_action_candidates(text)
    assert candidates
    assert candidates[0].statement_type == "PROPOSAL_COMMITMENT"
    client = ScriptedAI(lambda prompt: {
        "selected_ids": [record["id"] for record in json.loads(prompt.user)["candidates"]]
    })
    result = asyncio.run(ActionTaskAnalyzer(client, CONFIG).analyze(text))
    assert result.result["task_suggestions"] == []


def test_general_rule_obligation_is_not_created_as_live_project_task():
    text = "행정안전부 예규 계약 일반조건\n계약상대자는 보고서를 작성하여 제출하여야 한다."
    candidates = find_action_candidates(text)
    assert candidates[0].actor_scope == "GENERIC_RULE"
    client = ScriptedAI(lambda prompt: {
        "selected_ids": [record["id"] for record in json.loads(prompt.user)["candidates"]]
    })
    result = asyncio.run(ActionTaskAnalyzer(client, CONFIG).analyze(text))
    assert result.result["task_suggestions"] == []


def test_recurrence_and_month_only_schedule_keep_semantics_without_invented_day():
    text = "계약상대자는 매월 수행현황을 보고하여야 한다. 선정자 발표: 2026년 10월 예정"
    client = ScriptedAI(lambda _: {"items": []})
    result = asyncio.run(ScheduleAnalyzer(client, CONFIG).analyze(text))
    items = result.result["schedule_items"]
    recurrence = next(item for item in items if item["temporal_type"] == "RECURRENCE")
    assert recurrence["relative_expression"].startswith("매월")
    month = next(item for item in items if item["temporal_type"] == "MONTH_ONLY")
    assert month["starts_on"] is None and month["ends_on"] is None
    assert month["precision"] == "MONTH" and month["tentative"] is True


def test_tbd_schedule_is_preserved_without_inventing_date():
    client = ScriptedAI(lambda _: {"items": []})
    result = asyncio.run(ScheduleAnalyzer(client, CONFIG).analyze("평가 일정은 별도 통보합니다."))
    item = result.result["schedule_items"][0]
    assert item["temporal_type"] == "TBD"
    assert item["starts_on"] is None and item["ends_on"] is None
