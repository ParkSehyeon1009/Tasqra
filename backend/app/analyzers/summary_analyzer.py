"""짧은 원문은 1회, 긴 원문은 근거 추출 → 근거 선택 → 최종 요약한다."""
import logging
import re

from app.analyzers.output_schemas import FactsOutput, GroundedSummaryOutput, SelectionOutput, SummaryOutput
from app.analyzers.prompt_input import PromptBudget, encoded_size, split_document
from app.analyzers.prompts import (
    FACTS_SYSTEM_PROMPT, FINAL_SYSTEM_PROMPT, SELECT_SYSTEM_PROMPT,
    SUMMARY_PROMPT_VERSION, build_summary_prompt, request,
)
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)

# 글자와 글자 사이에 있어도 «같은 인용» 으로 볼 것들: 공백류와 보이지 않는 제어문자.
# 추출기는 `단,   평가참고자료` 처럼 공백을 여러 칸 뱉는데 모델은 한 칸으로 줄여
# 쓴다. 사람 눈에는 같은 문장이지만 글자 단위 대조는 실패한다.
_GAP = r"(?:\s|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f])*"


def normalize_summary(text: str) -> tuple[str, list[str]]:
    """깨진 마지막 문장과 비한국어 문자 누출을 조용히 정상 결과로 위장하지 않는다."""
    value = re.sub(r"\s+", " ", text).strip()
    warnings = []
    if re.search(r"[一-龥]", value):
        warnings.append("unexpected_cjk")
    if not re.search(r"(?:다|요|임|함|됨|음|것이다|있다|없다)[.!?]?$", value):
        completed = list(re.finditer(r"(?:다|요|임|함|됨|음|것이다|있다|없다)[.!?](?=\s|$)", value))
        if completed:
            value = value[:completed[-1].end()].strip()
            warnings.append("incomplete_tail_removed")
        else:
            warnings.append("possibly_incomplete")
    return value, warnings


def find_span(quote: str, text: str) -> tuple[int, int] | None:
    """인용이 원문의 어디에 있는지 (시작, 끝) 을 준다. 없으면 None.

    공백 개수 차이는 같은 것으로 본다. 대신 **호출한 쪽이 원문 글자를 잘라
    쓰도록** 위치를 준다 — 모델이 쓴 문자열을 그대로 저장하면 «저장된 인용은
    원문에 있다» 는 보장이 깨지기 때문이다. 느슨하게 통과시키는 것이 아니라
    원문 쪽으로 끌어당기는 것이다.
    """
    letters = [c for c in quote if not re.fullmatch(_GAP, c)]
    if not letters:
        return None
    # 공백류와 글자는 서로 겹치지 않으므로 되짚기(backtracking)가 일어나지 않는다.
    found = re.search(_GAP.join(re.escape(c) for c in letters), text)
    return (found.start(), found.end()) if found else None


def facts_request(text, start, end):
    return request(FACTS_SYSTEM_PROMPT, {"document": text, "start": start, "end": end}, SUMMARY_PROMPT_VERSION)


def final_request(records):
    return request(FINAL_SYSTEM_PROMPT, {"records": records}, SUMMARY_PROMPT_VERSION)


def selection_limit(records, limit):
    return max(1, min(len(records) // 2, limit // max(encoded_size(r) for r in records)))


def selection_request(records, limit):
    max_records = selection_limit(records, limit)
    return request(SELECT_SYSTEM_PROMPT, {"records": records, "selection_budget_bytes": limit,
        "max_records": max_records}, SUMMARY_PROMPT_VERSION)


class SummaryAnalyzer:
    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        budget = PromptBudget(self._settings)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        direct = build_summary_prompt(text)
        scope = {"truncated": False, "original_chars": len(text), "included_chars": len(text)}
        if len(text) <= budget.max_chars and budget.fits(direct):
            runner.progress("문서 요약", 0, 1)
            parsed = await runner.call(direct, SummaryOutput, stage="문서 요약")
            runner.progress("문서 요약", 1, 1)
            summary, warnings = normalize_summary(parsed.summary)
            output = {**parsed.model_dump(), "summary": summary, "quality_warnings": warnings,
                      "strategy": "direct", "input_scope": scope}
        else:
            chunks = split_document(text, budget, facts_request,
                overlap=self._settings.AI_CHUNK_OVERLAP_CHARS, max_chunks=self._settings.AI_MAX_CHUNKS)
            records = []
            seen = set()
            empty_chunks = []
            rejected = 0
            for i, chunk in enumerate(chunks):
                stage = f"근거 추출 {i + 1}/{len(chunks)}"
                runner.progress(stage, i, len(chunks))
                parsed = await runner.call(facts_request(chunk.text, chunk.start, chunk.end),
                    FactsOutput, stage=stage)
                # 인용을 원문에서 찾아 **원문 글자로 바꿔 담는다.** 못 찾은 것만
                # 버린다.
                #
                # 전에는 하나만 어긋나도 ValueError 로 구간을 통째로 버렸다. 근거
                # 6개 중 5개가 멀쩡한데 5개까지 잃었고, 구간이 10개면 그중 하나만
                # 걸려도 문서 분석 전체가 실패했다. 실제로 그렇게 실패했다.
                #
                # ⚠️ 재시도로는 못 고친다. local_client 가 temperature=0 으로
                #   고정하므로 같은 프롬프트에 **같은 답이 그대로 다시 온다**
                #   (3회 호출 실측: 서로 다른 답 1종). 그래서 runner 의 validate
                #   콜백을 쓰지 않는다 — 재시도는 시간만 두 배로 쓴다.
                dropped = 0
                for fact in parsed.facts:
                    span = find_span(fact.quote, chunk.text)
                    if span is None:
                        dropped += 1
                        continue
                    # ⚠️ fact.quote 가 아니라 원문에서 잘라낸 것을 담는다. 공백
                    #   개수가 다를 수 있고, 그대로 담으면 «저장된 인용은 원문에
                    #   있다» 는 보장이 깨진다(record 의 start~end 로 원문을
                    #   잘랐을 때 quote 와 달라진다).
                    quote = chunk.text[span[0]:span[1]]
                    # 다른 위치에 같은 문장이 있으면 같은 근거로 간주하지 않는다.
                    start = chunk.start + span[0]
                    key = (start, quote, fact.status)
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append({"id": f"e{len(records) + 1}", "quote": quote,
                        "status": fact.status, "start": start, "end": start + len(quote)})
                if dropped:
                    rejected += dropped
                    # 조용히 버리지 않는다. 원문 인용을 못 하는 모델을 쓰고 있다는
                    # 사실 자체가 신호다(파인튜닝 모델의 다국어 누출에서 나왔다).
                    logger.warning("원문에서 찾지 못한 인용 %d/%d개를 버렸다 stage=%s",
                        dropped, len(parsed.facts), stage)
                if dropped == len(parsed.facts):
                    empty_chunks.append(i + 1)
                runner.progress(stage, i + 1, len(chunks))
            records.sort(key=lambda r: r["start"])
            extracted_count = len(records)
            if not records:
                raise BusinessError(ErrorCode.AI_INVALID_RESPONSE, "전체 구간에서 요약 근거를 확보하지 못했습니다.")
            records, levels = await self._reduce(records, runner, budget)
            available = {r["id"] for r in records}
            def verify_final(parsed):
                if len(set(parsed.evidence_ids)) != len(parsed.evidence_ids) or not set(parsed.evidence_ids) <= available:
                    raise ValueError("unknown or duplicated evidence id")
            runner.progress("최종 요약", 0, 1)
            parsed = await runner.call(final_request(records), GroundedSummaryOutput,
                validate=verify_final, stage="최종 요약")
            runner.progress("최종 요약", 1, 1)
            summary, warnings = normalize_summary(parsed.summary)
            output = {**parsed.model_dump(), "summary": summary, "quality_warnings": warnings,
                "strategy": "hierarchical", "input_scope": scope,
                "chunk_count": len(chunks), "hard_split_count": sum(c.hard_split for c in chunks),
                "empty_evidence_chunks": empty_chunks, "extracted_evidence_count": extracted_count,
                # 원문에 없어서 버린 근거 수. 이 값이 크면 모델이 인용을 못 하고
                # 있다는 뜻이므로, 요약이 나왔더라도 근거가 얇다는 신호로 읽어야 한다.
                "rejected_evidence_count": rejected,
                "reduction_levels": levels, "evidence": records}
        return AnalyzeResult(result={**output, "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=SUMMARY_PROMPT_VERSION, **runner.metadata())

    async def _reduce(self, records, runner, budget):
        levels = 0
        while not budget.fits(final_request(records)):
            levels += 1
            if levels > 8:
                raise BusinessError(ErrorCode.AI_INPUT_TOO_LARGE)
            groups, group = [], []
            for record in records:
                if not budget.fits(selection_request([record], 999999)):
                    raise BusinessError(ErrorCode.AI_INPUT_TOO_LARGE)
                if group and not budget.fits(selection_request(group + [record], 999999)):
                    groups.append(group)
                    group = []
                group.append(record)
            if group:
                groups.append(group)
            reduced = []
            for index, group in enumerate(groups):
                if len(group) == 1:
                    reduced.extend(group)
                    continue
                limit = max(max(encoded_size(r) for r in group), sum(encoded_size(r) for r in group) // 2)
                allowed = {r["id"]: r for r in group}
                max_selected = selection_limit(group, limit)
                def verify(parsed):
                    ids = parsed.selected_ids
                    if len(set(ids)) != len(ids) or not set(ids) <= allowed.keys():
                        raise ValueError("unknown or duplicate evidence id")
                    if len(ids) > max_selected:
                        raise ValueError("too many selected records")
                    if sum(encoded_size(allowed[id]) for id in ids) > limit:
                        raise ValueError("selection exceeds budget")
                stage = f"근거 통합 {levels}단계 {index + 1}/{len(groups)}"
                runner.progress(stage, index, len(groups))
                parsed = await runner.call(selection_request(group, limit), SelectionOutput,
                    validate=verify, stage=stage)
                chosen = set(parsed.selected_ids)
                reduced.extend(r for r in group if r["id"] in chosen)
                runner.progress(stage, index + 1, len(groups))
            if len(reduced) >= len(records):
                raise BusinessError(ErrorCode.AI_INPUT_TOO_LARGE, "근거를 입력 예산 내로 통합하지 못했습니다.")
            records = reduced
        return records, levels
