# ① 책임: 금액 analyzer의 schema·parser·후보 문맥·registry 계약을 검증한다.
# ② 관계: AmountAnalyzer, API/worker registry와 FakeAIClient를 DB 없이 함께 검사한다.
# ③ Spring 비교: 외부 AI Bean을 fake로 바꾼 @Service 단위 테스트에 해당한다.

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ai.client_protocol import AIResult
from app.ai.fake_client import FakeAIClient
from app.analyzers.amount_analyzer import (
    AmountAnalyzer,
    _build_amount_prompt,
    _select_amount_contexts,
)
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.schemas.amount import AmountExtractionOut


@pytest.fixture
def config():
    return SimpleNamespace(
        AI_CONTEXT_TOKENS=8192,
        AI_MAX_OUTPUT_TOKENS=1536,
        AI_MAX_INPUT_CHARS=600,
        AI_CHUNK_OVERLAP_CHARS=60,
        AI_MAX_CHUNKS=256,
        AI_CHUNK_RETRIES=0,
        AI_TIMEOUT_SECONDS=5,
    )


class FakeAmountAI:
    provider = "test"
    model_name = "current-default-model"

    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    async def generate_with_meta(self, prompt):
        self.requests.append(prompt)
        answer = self.answer(prompt) if callable(self.answer) else self.answer
        text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        return AIResult(
            text=text,
            model_name=self.model_name,
            tokens_in=10,
            tokens_out=20,
            latency_ms=30,
        )


def _valid_payload():
    return {
        "document_type": "COST_SHEET",
        "currency": "KRW",
        "stated_total": "97,500,000원",
        "items": [{
            "item_name": "특급기술자",
            "category": "DIRECT_LABOR",
            "quantity": "3인월",
            "unit": "인월",
            "unit_price": "9,500,000원",
            "amount": "28,500,000원",
            "period_from": None,
            "period_to": None,
            "source_quote": "특급기술자 3인월 단가 9,500,000원 금액 28,500,000원",
            "confidence": 0.95,
            "reason": "산출내역서의 같은 행에 값이 기재되어 있음",
        }],
        "notes": None,
    }


def test_amount_analyzer_uses_schema_and_parser_normalization(config):
    client = FakeAmountAI(_valid_payload())
    source = "합계 97,500,000원\n특급기술자 3인월 단가 9,500,000원 금액 28,500,000원"

    result = asyncio.run(AmountAnalyzer(client, config).analyze(source))

    assert client.requests[0].response_schema is AmountExtractionOut
    assert client.requests[0].response_format()["json_schema"]["name"] == "AmountExtractionOut"
    assert "사업 예산" in client.requests[0].system
    assert "표가 없다는 이유로 items를 빈 배열" in client.requests[0].system
    assert "stated_total에도 넣으세요" in client.requests[0].system
    assert "item_name, category, quantity" in client.requests[0].system
    assert "100,000,000" not in client.requests[0].system
    prompt_data = json.loads(client.requests[0].user)
    assert prompt_data["allowed_source_quotes"] == source.splitlines()
    assert client.requests[0].prompt_version == "amount-v6"
    assert result.model_name == "current-default-model"
    assert result.result["stated_total"] == 97_500_000
    assert result.result["items"][0]["quantity"] == "3"
    assert result.result["items"][0]["unit_price"] == 9_500_000
    assert result.result["items"][0]["item_name"] == "특급기술자"
    assert result.result["items"][0]["amount"] == 28_500_000


def test_amount_analyzer_replaces_model_quote_with_unique_amount_line(config):
    source = "사 업 예 산 금 칠십사억삼천만 원 (￦7,430,000,000, 부가세 포함)"
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": 7_430_000_000,
        "items": [{
            # 실제 모델이 반환한 것처럼 항목명에 금액 원문 전체가 붙은 형태다.
            "item_name": "사 업 예 산 금 칠십사억삼천만 원 (7,430,000,000, 부가세 포함)",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 7_430_000_000,
            "period_from": None,
            "period_to": None,
            # 현재 요약 모델이 실제로 보인 것처럼 원문과 다른 인용문을 반환한다.
            "source_quote": "사업 예산 7,430,000,000원",
            "confidence": 0.99,
            "reason": "사업 예산과 금액이 함께 명시되어 있음",
        }],
        "notes": None,
    }

    result = asyncio.run(AmountAnalyzer(FakeAmountAI(payload), config).analyze(source))

    assert result.result["items"][0]["item_name"] == "사업예산"
    assert result.result["items"][0]["source_quote"] == source
    assert result.result["items"][0]["amount"] == 7_430_000_000


def test_amount_analyzer_rejects_ambiguous_amount_lines(config):
    first = "참가 보증금 1,000,000원"
    second = "계약 보증금 1,000,000원"
    source = f"{first}\n{second}"
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": None,
        "items": [{
            "item_name": "보증금",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 1_000_000,
            "period_from": None,
            "period_to": None,
            "source_quote": first,
            "confidence": 0.99,
            "reason": "보증금이 명시되어 있음",
        }],
        "notes": None,
    }

    with pytest.raises(BusinessError) as exc:
        asyncio.run(AmountAnalyzer(FakeAmountAI(payload), config).analyze(source))

    assert exc.value.error_code is ErrorCode.AI_INVALID_RESPONSE


@pytest.mark.parametrize("source", [
    "금액 -10,000원",
    "금액 −10,000원",
    "금액 10000.50원",
    "금액 1234,567원",
    "금액 12,345,678,90원",
    "금액 10,000-원",
    "금액 10,000+원",
    "금액 ₩10,000-",
    "금액 코드A10000B",
])
def test_amount_analyzer_rejects_partial_numeric_token_grounding(config, source):
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": None,
        "items": [{
            "item_name": "금액",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 10_000,
            "period_from": None,
            "period_to": None,
            "source_quote": source,
            "confidence": 0.99,
            "reason": "잘못된 숫자 일부를 금액으로 반환",
        }],
        "notes": None,
    }

    with pytest.raises(BusinessError) as exc:
        asyncio.run(AmountAnalyzer(FakeAmountAI(payload), config).analyze(source))

    assert exc.value.error_code is ErrorCode.AI_INVALID_RESPONSE


def test_amount_analyzer_sends_only_amount_context_for_long_document(config):
    quote = "사 업 예 산 금 칠십사억삼천만 원 (￦7,430,000,000, 부가세 포함)"
    source = "\n".join([
        *(f"일반 입찰 안내 {index}" for index in range(80)),
        "사업 개요",
        quote,
        "계약 기간은 체결일로부터 24개월",
        *(f"제출 서류 안내 {index}" for index in range(80)),
    ])
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": 7_430_000_000,
        "items": [{
            "item_name": "사업 예산",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 7_430_000_000,
            "period_from": None,
            "period_to": None,
            "source_quote": quote,
            "confidence": 0.99,
            "reason": "사업 예산과 숫자 금액이 함께 명시되어 있음",
        }],
        "notes": None,
    }
    client = FakeAmountAI(payload)

    result = asyncio.run(AmountAnalyzer(client, config).analyze(source))

    assert len(client.requests) == 1
    sent = json.loads(client.requests[0].user)["document"]
    assert quote in sent
    assert "사업 개요" in sent
    assert "계약 기간" in sent
    assert "일반 입찰 안내 0" not in sent
    assert "제출 서류 안내 79" not in sent
    assert len(sent) < len(source) // 4
    assert result.result["items"][0]["amount"] == 7_430_000_000


def test_amount_analyzer_keeps_all_plain_integer_table_rows(config):
    last_row = "운영 지원 | 1 | 2500000 | 2500000"
    source = "\n".join([
        "항목 | 수량 | 단가 | 금액",
        "분석 설계 | 2 | 9500000 | 19000000",
        "개발 지원 | 3 | 7000000 | 21000000",
        "품질 검증 | 1 | 5000000 | 5000000",
        last_row,
    ])
    payload = {
        "document_type": "COST_SHEET",
        "currency": "KRW",
        "stated_total": None,
        "items": [{
            "item_name": "운영 지원",
            "category": "OTHER",
            "quantity": "1",
            "unit": None,
            "unit_price": 2_500_000,
            "amount": 2_500_000,
            "period_from": None,
            "period_to": None,
            "source_quote": last_row,
            "confidence": 0.99,
            "reason": "표 행에 단가와 금액이 명시되어 있음",
        }],
        "notes": None,
    }
    client = FakeAmountAI(payload)

    result = asyncio.run(AmountAnalyzer(client, config).analyze(source))

    assert len(client.requests) == 1
    sent = json.loads(client.requests[0].user)["document"]
    assert "분석 설계 | 2 | 9500000 | 19000000" in sent
    assert last_row in sent
    assert result.result["items"][0]["amount"] == 2_500_000


def test_amount_analyzer_keeps_plain_integer_rows_after_row_100():
    rows = [f"항목 {index} | 1 | {2000000 + index} | {2000000 + index}"
            for index in range(105)]
    source = "\n".join(["항목 | 수량 | 단가 | 금액", *rows])

    contexts = _select_amount_contexts(source)
    selected = "".join(context.text for context in contexts)

    assert rows[0] in selected
    assert rows[-1] in selected


def test_amount_analyzer_ignores_dates_and_ids_outside_amount_context(config):
    quote = "사 업 예 산 7,430,000,000원"
    source = "\n".join([
        "사업 일정은 2026년에 시작",
        "예산 편성 관련 공고번호 202609071234",
        "예상 금액  안내",
        "공고번호  202609071234",
        *(f"일반 제출 안내 {index}" for index in range(30)),
        quote,
        "부가세 포함",
    ])
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": 7_430_000_000,
        "items": [{
            "item_name": "사업 예산",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 7_430_000_000,
            "period_from": None,
            "period_to": None,
            "source_quote": quote,
            "confidence": 0.99,
            "reason": "사업 예산과 금액이 함께 명시되어 있음",
        }],
        "notes": None,
    }
    client = FakeAmountAI(payload)

    result = asyncio.run(AmountAnalyzer(client, config).analyze(source))

    assert len(client.requests) == 1
    sent = json.loads(client.requests[0].user)["document"]
    assert quote in sent
    assert "공고번호" not in sent
    assert "예상 금액  안내" not in sent
    assert result.result["items"][0]["amount"] == 7_430_000_000


def test_amount_analyzer_sends_empty_document_when_no_candidate_exists(config):
    source = "\n".join(f"일반 입찰 안내 {index}" for index in range(200))
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": None,
        "items": [],
        "notes": None,
    }
    client = FakeAmountAI(payload)

    result = asyncio.run(AmountAnalyzer(client, config).analyze(source))

    assert len(client.requests) == 1
    assert json.loads(client.requests[0].user)["document"] == ""
    assert result.result["items"] == []


def test_amount_analyzer_keeps_distant_candidate_windows_separate(config):
    first_quote = "참가 보증금 1,000,000원"
    amount_quote = "계약 보증금 50,000,000원"
    source = "\n".join([
        first_quote,
        "참가 신청 시 납부",
        *(f"일반 계약 안내 {index}" for index in range(20)),
        "보증 조건",
        amount_quote,
        "납부 기한은 계약 체결 후 안내",
    ])

    def answer(prompt):
        document = json.loads(prompt.user)["document"]
        items = []
        if amount_quote in document:
            items.append({
                "item_name": "계약 보증금",
                "category": "OTHER",
                "quantity": None,
                "unit": None,
                "unit_price": None,
                "amount": 50_000_000,
                "period_from": None,
                "period_to": None,
                "source_quote": amount_quote,
                "confidence": 0.99,
                "reason": "보증금과 숫자 금액이 함께 명시되어 있음",
            })
        return {
            "document_type": "RFP",
            "currency": "KRW",
            "stated_total": None,
            "items": items,
            "notes": None,
        }

    client = FakeAmountAI(answer)
    result = asyncio.run(AmountAnalyzer(client, config).analyze(source))

    assert len(client.requests) == 2
    sent_documents = [json.loads(request.user)["document"] for request in client.requests]
    assert all(not (first_quote in document and amount_quote in document)
               for document in sent_documents)
    assert result.result["items"][0]["item_name"] == "계약 보증금"


def test_amount_analyzer_rejects_quote_from_another_candidate_window(config):
    first_quote = "참가 보증금 1,000,000원"
    other_quote = "계약 보증금 50,000,000원"
    source = "\n".join([
        first_quote,
        "참가 신청 시 납부",
        *(f"일반 계약 안내 {index}" for index in range(20)),
        "보증 조건",
        other_quote,
    ])
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": None,
        "items": [{
            "item_name": "계약 보증금",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 50_000_000,
            "period_from": None,
            "period_to": None,
            "source_quote": other_quote,
            "confidence": 0.99,
            "reason": "다른 후보 창의 금액을 잘못 인용",
        }],
        "notes": None,
    }

    with pytest.raises(BusinessError) as exc:
        asyncio.run(AmountAnalyzer(FakeAmountAI(payload), config).analyze(source))

    assert exc.value.error_code is ErrorCode.AI_INVALID_RESPONSE


def test_amount_analyzer_rejects_quote_when_allowed_lines_are_empty(config):
    source = "금액 1,000원 " + ("A" * 1100)
    config.AI_MAX_INPUT_CHARS = 2000
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": None,
        "items": [{
            "item_name": "금액",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 1_000,
            "period_from": None,
            "period_to": None,
            "source_quote": "금액 1,000원",
            "confidence": 0.99,
            "reason": "긴 줄의 일부만 인용",
        }],
        "notes": None,
    }

    with pytest.raises(BusinessError) as exc:
        asyncio.run(AmountAnalyzer(FakeAmountAI(payload), config).analyze(source))

    assert exc.value.error_code is ErrorCode.AI_INVALID_RESPONSE


def test_late_candidate_is_sized_with_original_source_range(config):
    quote = "금액 1,000원"
    candidate_context = f"{'A' * 400}\n{quote}"
    source = ("일반 안내\n" * 20_000) + candidate_context
    base = source.index("A" * 400)
    local_prompt = _build_amount_prompt(candidate_context, 0, len(candidate_context))
    actual_prompt = _build_amount_prompt(
        candidate_context, base, base + len(candidate_context))
    prompt_size = lambda prompt: (
        len(prompt.system.encode("utf-8"))
        + len(prompt.user.encode("utf-8"))
        + config.AI_MAX_OUTPUT_TOKENS
        + 256
    )
    config.AI_CONTEXT_TOKENS = prompt_size(local_prompt)
    assert prompt_size(actual_prompt) > config.AI_CONTEXT_TOKENS

    def answer(prompt):
        document = json.loads(prompt.user)["document"]
        items = []
        if quote in document:
            items.append({
                "item_name": "금액",
                "category": "OTHER",
                "quantity": None,
                "unit": None,
                "unit_price": None,
                "amount": 1_000,
                "period_from": None,
                "period_to": None,
                "source_quote": quote,
                "confidence": 0.99,
                "reason": "금액이 숫자와 함께 명시되어 있음",
            })
        return {
            "document_type": "RFP",
            "currency": "KRW",
            "stated_total": None,
            "items": items,
            "notes": None,
        }

    client = FakeAmountAI(answer)
    result = asyncio.run(AmountAnalyzer(client, config).analyze(source))

    assert len(client.requests) >= 2
    assert all(prompt_size(request) <= config.AI_CONTEXT_TOKENS
               for request in client.requests)
    assert min(json.loads(request.user)["source_range"]["start"]
               for request in client.requests) == base
    assert result.result["items"][0]["amount"] == 1_000


def test_document_level_budget_is_an_item_even_without_cost_table(config):
    source = "사업 예산 100,000,000원(부가세 포함)"
    payload = {
        "document_type": "RFP",
        "currency": "KRW",
        "stated_total": 100_000_000,
        "items": [{
            "item_name": "사업 예산",
            "category": "OTHER",
            "quantity": None,
            "unit": None,
            "unit_price": None,
            "amount": 100_000_000,
            "period_from": None,
            "period_to": None,
            "source_quote": source,
            "confidence": 0.99,
            "reason": "사업 예산과 숫자 금액이 본문에 명시되어 있음",
        }],
        "notes": None,
    }

    result = asyncio.run(AmountAnalyzer(FakeAmountAI(payload), config).analyze(source))

    assert result.result["stated_total"] == 100_000_000
    assert result.result["items"] == [{
        "item_name": "사업예산",
        "category": "OTHER",
        "quantity": None,
        "unit": None,
        "unit_price": None,
        "amount": 100_000_000,
        "period_from": None,
        "period_to": None,
        "source_quote": source,
        "confidence": 0.99,
        "reason": "사업 예산과 숫자 금액이 본문에 명시되어 있음",
    }]


def test_amount_analyzer_must_call_parse_amount_extraction(config, monkeypatch):
    import app.analyzers.amount_analyzer as module

    real_parser = module.parse_amount_extraction
    parser = MagicMock(side_effect=real_parser)
    monkeypatch.setattr(module, "parse_amount_extraction", parser)
    source = "합계 97,500,000원\n특급기술자 3인월 단가 9,500,000원 금액 28,500,000원"

    asyncio.run(AmountAnalyzer(FakeAmountAI(_valid_payload()), config).analyze(source))

    parser.assert_called_once()
    assert isinstance(parser.call_args.args[0], AIResult)


@pytest.mark.parametrize("answer", [
    "```json\n{}\n```",
    '{"document_type":"COST_SHEET",',
    {**_valid_payload(), "unexpected": "value"},
])
def test_amount_analyzer_rejects_parser_invalid_responses(config, answer):
    with pytest.raises(BusinessError) as exc:
        asyncio.run(AmountAnalyzer(FakeAmountAI(answer), config).analyze("금액 문서"))

    assert exc.value.error_code is ErrorCode.AI_INVALID_RESPONSE


def test_amount_analyzer_rejects_invented_source_quote(config):
    with pytest.raises(BusinessError) as exc:
        asyncio.run(AmountAnalyzer(FakeAmountAI(_valid_payload()), config).analyze("다른 원문"))

    assert exc.value.error_code is ErrorCode.AI_INVALID_RESPONSE


def test_amount_timeout_is_logged_without_document_or_response(config, caplog):
    class SlowAI:
        provider = "test"
        model_name = "slow-model"

        async def generate_with_meta(self, prompt):
            await asyncio.sleep(0.05)

    timeout_config = SimpleNamespace(**vars(config))
    timeout_config.AI_TIMEOUT_SECONDS = 0.01

    with caplog.at_level("WARNING", logger="app.analyzers.runner"):
        with pytest.raises(BusinessError) as exc:
            asyncio.run(AmountAnalyzer(SlowAI(), timeout_config).analyze(
                "사업 예산 100,000,000원"))

    assert exc.value.error_code is ErrorCode.AI_TIMEOUT
    assert "AI 호출 시간 초과" in caplog.text
    assert "timeout_seconds=0.01" in caplog.text
    assert "100,000,000원" not in caplog.text


def test_fake_ai_client_has_valid_amount_response(config):
    result = asyncio.run(AmountAnalyzer(FakeAIClient(), config).analyze("금액이 없는 문서"))

    assert result.result == {
        "document_type": "ETC",
        "currency": "KRW",
        "stated_total": None,
        "items": [],
        "notes": "테스트용 fake 응답입니다.",
    }


def test_api_and_worker_registries_include_amount_with_default_client():
    from app.dependencies import get_analyzer_registry
    from app.services.analysis_service import DEFAULT_ANALYZER_TYPES
    from app.worker import _build_worker_analyzer_registry

    # 세현님의 최신 정책을 유지한다. features와 amount는 등록만 하고 명시 호출한다.
    assert "features" not in DEFAULT_ANALYZER_TYPES
    assert "amount" not in DEFAULT_ANALYZER_TYPES

    get_analyzer_registry.cache_clear()
    api_registry = get_analyzer_registry()
    assert isinstance(api_registry["amount"], AmountAnalyzer)

    summary, category, decision, schedule, default = (object() for _ in range(5))
    worker_registry = _build_worker_analyzer_registry(
        summary, category, decision, schedule, default)
    assert isinstance(worker_registry["amount"], AmountAnalyzer)
    assert worker_registry["amount"]._ai_client is default
