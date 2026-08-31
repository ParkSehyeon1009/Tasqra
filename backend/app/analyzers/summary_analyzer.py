"""짧은 원문은 1회, 긴 원문은 근거 추출 → 근거 선택 → 최종 요약한다."""
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
            output = {**parsed.model_dump(), "strategy": "direct", "input_scope": scope}
        else:
            chunks = split_document(text, budget, facts_request,
                overlap=self._settings.AI_CHUNK_OVERLAP_CHARS, max_chunks=self._settings.AI_MAX_CHUNKS)
            records = []
            seen = set()
            empty_chunks = []
            for i, chunk in enumerate(chunks):
                stage = f"근거 추출 {i + 1}/{len(chunks)}"
                runner.progress(stage, i, len(chunks))
                def verify(parsed):
                    if any(f.quote not in chunk.text for f in parsed.facts):
                        raise ValueError("quote is not an exact source substring")
                parsed = await runner.call(facts_request(chunk.text, chunk.start, chunk.end),
                    FactsOutput, validate=verify, stage=stage)
                if not parsed.facts:
                    empty_chunks.append(i + 1)
                for fact in parsed.facts:
                    # 다른 위치에 같은 문장이 있으면 같은 근거로 간주하지 않는다.
                    start = chunk.start + chunk.text.index(fact.quote)
                    key = (start, fact.quote, fact.status)
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append({"id": f"e{len(records) + 1}", "quote": fact.quote,
                        "status": fact.status, "start": start, "end": start + len(fact.quote)})
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
            output = {**parsed.model_dump(), "strategy": "hierarchical", "input_scope": scope,
                "chunk_count": len(chunks), "hard_split_count": sum(c.hard_split for c in chunks),
                "empty_evidence_chunks": empty_chunks, "extracted_evidence_count": extracted_count,
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
