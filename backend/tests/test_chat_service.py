# =============================================================================
# 이 파일의 책임: 문서 기반 질의응답 챗봇(CHAT-001)의 권한 재사용·빈 검색·프롬프트
#   예산·LLM 근거 번호 매핑을 DB와 실제 모델 없이 검증한다.
# 다른 파일과의 관계: ChatService에 SearchService·ChunkRepository·AI client fake를
#   주입하고 context_assembly의 구분자 포함 예산 보장도 함께 고정한다.
# Spring 비교: Mockito 대역으로 애플리케이션 Service를 검증하는 단위 테스트다.
# =============================================================================

import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ai.client_protocol import AIResult
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.repositories.chunk_repository import ChunkRepository
from app.services.chat_service import (
    CHAT_MESSAGE_FRAMING_RESERVE_TOKENS,
    ChatService,
)
from app.services.context_assembly import ContextChunk, assemble_context
from app.services.token_counting import Utf8ByteTokenCounter


class _FakeAI:
    provider = "fake"
    model_name = "fake-chat"

    def __init__(self, *, evidence_ids=(1,), answerable=True) -> None:
        self.evidence_ids = list(evidence_ids)
        self.answerable = answerable
        self.requests = []

    async def generate_with_meta(self, prompt):
        self.requests.append(prompt)
        return AIResult(
            text=json.dumps(
                {
                    "answer": "문서 근거에 따른 답변입니다.",
                    "answerable": self.answerable,
                    "evidence_ids": self.evidence_ids,
                },
                ensure_ascii=False,
            ),
            model_name=self.model_name,
            tokens_in=100,
            tokens_out=20,
        )


class _LengthCounter:
    name = "test-length"
    is_exact = True

    def count(self, text):
        return len(text)


def _settings(**overrides):
    values = {
        "CONTEXT_MAX_EVIDENCES": 8,
        "CONTEXT_BUDGET_TOKENS": 4000,
        "AI_CONTEXT_TOKENS": 8192,
        "AI_MAX_OUTPUT_TOKENS": 1536,
        "AI_TIMEOUT_SECONDS": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _search_item(chunk_id, *, document_id=10, seq=0):
    return SimpleNamespace(chunk_id=chunk_id, document_id=document_id, seq=seq)


def _search_response(items=()):
    return SimpleNamespace(
        results=list(items),
        searched_project_ids=[1],
        embedding_model="embedding-model",
    )


def _chunk(chunk_id, text, *, document_id=10, seq=0, filename="계약서.pdf"):
    model = SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        seq=seq,
        text=text,
        page_number=2,
        content_start=100 + seq * 50,
        content_end=100 + seq * 50 + len(text),
    )
    return (model, filename, 1, "테스트 프로젝트")


def _amount_item(name, quantity, unit_price, amount, *, unit="인월"):
    row = f"{name} | {quantity} / {unit} | {unit_price:,} | {amount:,}"
    return SimpleNamespace(
        item_name=name,
        quantity=Decimal(str(quantity)),
        unit=unit,
        unit_price=Decimal(str(unit_price)),
        amount=Decimal(str(amount)),
        currency="KRW",
        source_quote=row,
    )


def _service(
    *,
    search_response,
    rows=(),
    amount_rows=(),
    ai=None,
    settings=None,
    counter=None,
):
    search = MagicMock()
    search.search_hybrid.return_value = search_response
    repository = MagicMock()
    repository.get_context_rows.return_value = list(rows)
    amount_repository = MagicMock()
    amount_repository.list_project_items.return_value = list(amount_rows)
    ai = ai or _FakeAI()
    service = ChatService(
        search_service=search,
        chunk_repository=repository,
        amount_repository=amount_repository,
        ai_client=ai,
        settings=settings or _settings(),
        token_counter=counter or Utf8ByteTokenCounter(),
    )
    return service, search, repository, ai


def test_non_member_project_is_blocked_before_context_or_llm():
    service, search, repository, ai = _service(search_response=_search_response())
    search.search_hybrid.side_effect = BusinessError(ErrorCode.PROJECT_NOT_FOUND)

    with pytest.raises(BusinessError) as error:
        asyncio.run(service.ask(user_id=7, project_id=999, question="지급 기한은?"))

    assert error.value.error_code is ErrorCode.PROJECT_NOT_FOUND
    repository.get_context_rows.assert_not_called()
    assert ai.requests == []
    requested = search.search_hybrid.call_args.args[1]
    assert requested.project_ids == [999]


def test_no_search_results_returns_without_calling_llm():
    service, _, repository, ai = _service(search_response=_search_response())

    response = asyncio.run(
        service.ask(user_id=7, project_id=1, question="관련 규정은?")
    )

    assert response.evidence == []
    assert "근거를 찾지 못했습니다" in response.answer
    repository.get_context_rows.assert_not_called()
    assert ai.requests == []


def test_unit_price_question_uses_approved_amount_columns_without_llm():
    table = (
        "항목 | 투입량 | 기준 단가 | 합계\n"
        "특급기술자 | 3 / 인 / 월 | 9,500,000 | 28,500,000"
    )
    item = SimpleNamespace(
        item_name="특급기술자",
        quantity=Decimal("3"),
        unit="인월",
        unit_price=Decimal("9500000"),
        amount=Decimal("28500000"),
        currency="KRW",
        source_quote="특급기술자 | 3 / 인 / 월 | 9,500,000 | 28,500,000",
    )
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, table, filename="[TEST] 산출내역서.pdf")],
        amount_rows=[(item, 10, "[TEST] 산출내역서.pdf")],
        ai=ai,
    )

    response = asyncio.run(
        service.ask(
            user_id=7,
            project_id=1,
            question="특급기술자 1인당 인건비는 얼마야?",
        )
    )

    assert ai.requests == []
    assert "1인월당 단가는 9,500,000원" in response.answer
    assert "3인월 × 단가 9,500,000원 = 총액 28,500,000원" in response.answer
    assert response.evidence[0].document_filename == "[TEST] 산출내역서.pdf"


def test_named_multiple_technicians_return_each_verified_unit_price():
    table = (
        "항목 | 투입량 | 기준 단가 | 합계\n"
        "특급기술자 | 3 / 인 / 월 | 9,500,000 | 28,500,000\n"
        "고급기술자 | 6 / 인 / 월 | 7,200,000 | 43,200,000\n"
        "중급기술자 | 2 / 인 / 월 | 5,500,000 | 11,000,000"
    )
    items = [
        _amount_item("특급기술자", 3, 9_500_000, 28_500_000),
        _amount_item("고급기술자", 6, 7_200_000, 43_200_000),
        _amount_item("중급기술자", 2, 5_500_000, 11_000_000),
    ]
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, table, filename="[TEST] 산출내역서.pdf")],
        amount_rows=[(item, 10, "[TEST] 산출내역서.pdf") for item in items],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자, 고급기술자, 중급기술자 1인당 인건비는?",
    ))

    assert ai.requests == []
    assert "특급기술자: 1인월당 9,500,000원" in response.answer
    assert "고급기술자: 1인월당 7,200,000원" in response.answer
    assert "중급기술자: 1인월당 5,500,000원" in response.answer
    assert len(response.evidence) == 1


def test_technician_collection_question_returns_all_technician_rows_only():
    table = (
        "특급기술자 | 3 / 인 / 월 | 9,500,000 | 28,500,000\n"
        "고급기술자 | 6 / 인 / 월 | 7,200,000 | 43,200,000\n"
        "제경비 | 1 / 식 / 월 | 25,800,000 | 25,800,000"
    )
    technician_items = [
        _amount_item("특급기술자", 3, 9_500_000, 28_500_000),
        _amount_item("고급기술자", 6, 7_200_000, 43_200_000),
    ]
    overhead = _amount_item("제경비", 1, 25_800_000, 25_800_000)
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, table)],
        amount_rows=[
            *((item, 10, "계약서.pdf") for item in technician_items),
            (overhead, 10, "계약서.pdf"),
        ],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="기술자들별로 1인당 인건비 말해줘",
    ))

    assert ai.requests == []
    assert "특급기술자" in response.answer
    assert "고급기술자" in response.answer
    assert "제경비" not in response.answer


def test_duplicate_technician_name_across_evidence_documents_is_ambiguous():
    first = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    second = _amount_item("특급기술자", 2, 10_000_000, 20_000_000)
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([
            _search_item(11, document_id=10),
            _search_item(22, document_id=20),
        ]),
        rows=[
            _chunk(11, first.source_quote, document_id=10, filename="첫째.pdf"),
            _chunk(22, second.source_quote, document_id=20, filename="둘째.pdf"),
        ],
        amount_rows=[
            (first, 10, "첫째.pdf"),
            (second, 20, "둘째.pdf"),
        ],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자 1인당 인건비는?",
    ))

    assert ai.requests == []
    assert "단가를 하나로 확정하지 못했습니다" in response.answer
    assert response.evidence == []


def test_named_multiple_technicians_abstains_when_one_requested_row_is_missing():
    first = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    second = _amount_item("고급기술자", 6, 7_200_000, 43_200_000)
    table = f"{first.source_quote}\n{second.source_quote}"
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, table)],
        amount_rows=[(first, 10, "계약서.pdf"), (second, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자, 고급기술자, 중급기술자 1인당 인건비는?",
    ))

    assert ai.requests == []
    assert "단가를 하나로 확정하지 못했습니다" in response.answer
    assert response.evidence == []


def test_unique_technicians_from_different_documents_are_not_mixed():
    first = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    second = _amount_item("고급기술자", 6, 7_200_000, 43_200_000)
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([
            _search_item(11, document_id=10),
            _search_item(22, document_id=20),
        ]),
        rows=[
            _chunk(11, first.source_quote, document_id=10, filename="첫째.pdf"),
            _chunk(22, second.source_quote, document_id=20, filename="둘째.pdf"),
        ],
        amount_rows=[(first, 10, "첫째.pdf"), (second, 20, "둘째.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자, 고급기술자 1인당 인건비는?",
    ))

    assert ai.requests == []
    assert "단가를 하나로 확정하지 못했습니다" in response.answer
    assert response.evidence == []


def test_explicit_person_month_quantity_calculates_single_amount_without_llm():
    item = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, item.source_quote)],
        amount_rows=[(item, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자 2인월 인건비는?",
    ))

    assert ai.requests == []
    assert "특급기술자: 2인월 × 9,500,000원 = 19,000,000원" in response.answer
    assert len(response.evidence) == 1


def test_person_month_quantity_calculates_each_technician_amount():
    first = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    second = _amount_item("고급기술자", 6, 7_200_000, 43_200_000)
    table = f"{first.source_quote}\n{second.source_quote}"
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, table)],
        amount_rows=[(first, 10, "계약서.pdf"), (second, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="기술자들별로 2인월 인건비를 계산해줘",
    ))

    assert ai.requests == []
    assert "특급기술자: 2인월 × 9,500,000원 = 19,000,000원" in response.answer
    assert "고급기술자: 2인월 × 7,200,000원 = 14,400,000원" in response.answer


def test_person_count_without_duration_requests_person_month_quantity():
    item = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, item.source_quote)],
        amount_rows=[(item, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자 2명 인건비는?",
    ))

    assert ai.requests == []
    assert "인원 수만으로는 총 인건비를 계산할 수 없습니다" in response.answer
    assert "2인월" in response.answer
    assert response.evidence == []


def test_different_person_month_quantities_map_to_each_named_item():
    first = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    second = _amount_item("고급기술자", 6, 7_200_000, 43_200_000)
    third = _amount_item("중급기술자", 4, 5_800_000, 23_200_000)
    table = f"{first.source_quote}\n{second.source_quote}\n{third.source_quote}"
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, table)],
        amount_rows=[
            (first, 10, "계약서.pdf"),
            (second, 10, "계약서.pdf"),
            (third, 10, "계약서.pdf"),
        ],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question=(
            "특급기술자 2인월, 고급기술자 3인월, "
            "중급기술자 1.5인월 인건비는?"
        ),
    ))

    assert ai.requests == []
    assert "특급기술자: 2인월 × 9,500,000원 = 19,000,000원" in response.answer
    assert "고급기술자: 3인월 × 7,200,000원 = 21,600,000원" in response.answer
    assert "중급기술자: 1.5인월 × 5,800,000원 = 8,700,000원" in response.answer
    assert len(response.evidence) == 1


def test_duplicate_requested_name_abstains_even_when_only_one_has_quantity():
    first = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    second = _amount_item("고급기술자", 6, 7_200_000, 43_200_000)
    table = f"{first.source_quote}\n{second.source_quote}"
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, table)],
        amount_rows=[(first, 10, "계약서.pdf"), (second, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question=(
            "특급기술자와 특급기술자 2인월, "
            "고급기술자 3인월 인건비는?"
        ),
    ))

    assert ai.requests == []
    assert "단가를 하나로 확정하지 못했습니다" in response.answer
    assert response.evidence == []


def test_unpaired_multiple_person_months_request_explicit_item_mapping():
    item = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, item.source_quote)],
        amount_rows=[(item, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자 2인월과 3인월 인건비는?",
    ))

    assert ai.requests == []
    assert "인월 수량을 항목과 일대일로 연결하지 못했습니다" in response.answer
    assert response.evidence == []


def test_person_month_fact_question_does_not_trigger_amount_calculation():
    item = _amount_item("특급기술자", 3, 9_500_000, 28_500_000)
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, item.source_quote)],
        amount_rows=[(item, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자 투입 기간이 2인월이야?",
    ))

    assert len(ai.requests) == 1
    assert response.answer == "문서 근거에 따른 답변입니다."


def test_person_month_calculation_rejects_non_person_month_unit():
    item = _amount_item(
        "특급기술자",
        3,
        500_000,
        1_500_000,
        unit="인일",
    )
    ai = _FakeAI()
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, item.source_quote)],
        amount_rows=[(item, 10, "계약서.pdf")],
        ai=ai,
    )

    response = asyncio.run(service.ask(
        user_id=7,
        project_id=1,
        question="특급기술자 2인월 인건비는?",
    ))

    assert ai.requests == []
    assert "단가를 하나로 확정하지 못했습니다" in response.answer
    assert response.evidence == []


def test_final_evidence_and_full_prompt_fit_calculated_budget():
    text = " ".join(
        f"{index}번째 대금은 검수 완료 후 30일 이내 지급한다."
        for index in range(200)
    )
    row = _chunk(11, text)
    settings = _settings(
        AI_CONTEXT_TOKENS=2600,
        AI_MAX_OUTPUT_TOKENS=500,
        CONTEXT_BUDGET_TOKENS=1800,
    )
    counter = Utf8ByteTokenCounter()
    service, _, _, ai = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[row],
        settings=settings,
        counter=counter,
    )

    response = asyncio.run(
        service.ask(user_id=7, project_id=1, question="대금 지급 기한은?")
    )

    assert response.evidence_used_tokens <= response.evidence_budget_tokens
    prompt = ai.requests[0]
    assert (
        counter.count(prompt.system)
        + counter.count(prompt.user)
        + CHAT_MESSAGE_FRAMING_RESERVE_TOKENS
        + settings.AI_MAX_OUTPUT_TOKENS
        <= settings.AI_CONTEXT_TOKENS
    )


def test_separator_is_included_in_evidence_budget():
    counter = _LengthCounter()
    chunks = [
        ContextChunk(1, 10, "a.pdf", 0, "첫 번째 근거다."),
        ContextChunk(2, 20, "b.pdf", 0, "두 번째 근거다."),
    ]
    unlimited = assemble_context(chunks, budget_tokens=10_000, counter=counter)
    blocks = unlimited.text.split("\n\n")
    budget_without_separator = sum(counter.count(block) for block in blocks)

    result = assemble_context(
        chunks,
        budget_tokens=budget_without_separator,
        counter=counter,
    )

    assert len(result.evidences) == 1
    assert counter.count(result.text) == result.used_tokens
    assert counter.count(result.text) <= result.budget_tokens


def test_llm_evidence_id_maps_to_real_second_chunk_quote():
    first = _chunk(11, "첫 번째 문서의 고유한 근거다.", document_id=10, seq=0, filename="첫째.pdf")
    second = _chunk(22, "두 번째 문서의 선택된 원문 인용이다.", document_id=20, seq=3, filename="둘째.pdf")
    ai = _FakeAI(evidence_ids=(2,))
    service, _, _, _ = _service(
        search_response=_search_response([
            _search_item(11, document_id=10, seq=0),
            _search_item(22, document_id=20, seq=3),
        ]),
        rows=[second, first],
        ai=ai,
    )

    response = asyncio.run(
        service.ask(user_id=7, project_id=1, question="선택된 근거는?")
    )

    assert response.answer == "문서 근거에 따른 답변입니다."
    assert len(response.evidence) == 1
    evidence = response.evidence[0]
    assert evidence.evidence_id == 2
    assert evidence.chunk_id == 22
    assert evidence.document_id == 20
    assert evidence.document_filename == "둘째.pdf"
    assert evidence.quote == "두 번째 문서의 선택된 원문 인용이다."


def test_llm_cannot_reference_an_unassembled_evidence():
    ai = _FakeAI(evidence_ids=(99,))
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, "실제 근거다.")],
        ai=ai,
    )

    with pytest.raises(BusinessError) as error:
        asyncio.run(service.ask(user_id=7, project_id=1, question="근거는?"))

    assert error.value.error_code is ErrorCode.AI_INVALID_RESPONSE



def test_llm_may_abstain_without_inventing_an_evidence():
    ai = _FakeAI(evidence_ids=(), answerable=False)
    service, _, _, _ = _service(
        search_response=_search_response([_search_item(11)]),
        rows=[_chunk(11, "질문과 관련 없는 문서 내용이다.")],
        ai=ai,
    )

    response = asyncio.run(
        service.ask(user_id=7, project_id=1, question="문서에 없는 사실은?")
    )

    assert response.answer == "문서 근거에 따른 답변입니다."
    assert response.evidence == []



def test_context_query_requires_document_and_chunk_project_to_match():
    db = MagicMock()
    db.execute.return_value.all.return_value = []
    repository = ChunkRepository(db)

    repository.get_context_rows(
        chunk_ids=[11],
        project_ids=[1],
        embedding_model="embedding-model",
    )

    statement = str(db.execute.call_args.args[0])
    assert "documents.project_id = document_chunks.project_id" in statement
    assert "document_chunks.project_id =" in statement
    assert "documents.project_id =" in statement
