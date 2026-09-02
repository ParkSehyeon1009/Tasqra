import asyncio
from types import SimpleNamespace

from app.ai.fake_client import FakeAIClient
from app.ai.client_protocol import AIResult
from app.analyzers.action_candidate_finder import find_action_candidates
from app.analyzers.action_task_analyzer import ActionTaskAnalyzer
from app.analyzers.output_schemas import ActionSelectionOutput


def config():
    return SimpleNamespace(AI_CONTEXT_TOKENS=8192, AI_MAX_OUTPUT_TOKENS=1536,
        AI_MAX_INPUT_CHARS=6000, AI_CHUNK_OVERLAP_CHARS=60, AI_MAX_CHUNKS=256,
        AI_CHUNK_RETRIES=1, AI_TIMEOUT_SECONDS=5)


def test_candidate_finder_marks_form_examples_and_groups_guide_without_hard_drop():
    text = """
접수기간 : 2026. 9. 10. ~ 2026. 9. 20. 접수방법 : 방문접수 접수장소 : 시청
※ 신청인은 모든 서류를 준비하여 제출해야 함
【 공적조서 및 구비서류 작성시 유의사항 】
경력증명서와 건강보험 확인서를 반드시 제출하여야 함
[별지 제1호서식]
홍길동은 신청서를 작성해야 함
"""
    candidates = find_action_candidates(text)
    titles = [candidate.title for candidate in candidates]
    assert "신청 서류 방문 제출" in titles
    assert "필수 신청서류 작성 및 증빙자료 준비" in titles
    example = next(candidate for candidate in candidates if "홍길동" in candidate.text)
    assert example.section_type in {"form_or_appendix", "example"}
    assert example.quality_score < 0.7


def test_action_analyzer_only_returns_grounded_candidates():
    analyzer = ActionTaskAnalyzer(FakeAIClient(), config())
    result = asyncio.run(analyzer.analyze("신청인은 증빙자료를 준비하여 제출해야 합니다."))
    assert result.result["candidate_count"] == 1
    assert result.result["selected_count"] == 1
    assert result.result["task_suggestions"][0]["evidence_text"] in "신청인은 증빙자료를 준비하여 제출해야 합니다."


def test_no_action_candidate_skips_model_call():
    result = asyncio.run(ActionTaskAnalyzer(FakeAIClient(), config()).analyze(
        "이 문서는 사업의 개요를 설명합니다."))
    assert result.result == {"task_suggestions": [], "candidate_count": 0,
        "selected_count": 0, "call_count": 0}


class SelectAllAI(FakeAIClient):
    async def generate_with_meta(self, prompt):
        import json
        records = json.loads(prompt.user)["candidates"]
        payload = ActionSelectionOutput(
            selected_ids=[record["id"] for record in records]).model_dump_json()
        return AIResult(text=payload, model_name=self.model_name,
            tokens_in=1, tokens_out=1, latency_ms=1)


def test_selected_aggregate_suppresses_only_same_section_details():
    text = """
접수기간 : 2026. 9. 10.까지 접수방법 : 방문접수 접수장소 : 시청
【 공적조서 및 구비서류 작성시 유의사항 】
경력증명서를 반드시 제출하여야 함
건강보험 확인서를 반드시 첨부하여야 함
"""
    result = asyncio.run(ActionTaskAnalyzer(SelectAllAI(), config()).analyze(text))
    suggestions = result.result["task_suggestions"]
    assert [item["title"] for item in suggestions] == [
        "신청 서류 방문 제출", "필수 신청서류 작성 및 증빙자료 준비"]
