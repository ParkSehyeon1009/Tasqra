"""문서 전체를 구간으로 나눠 결정사항을 뽑고 원문 근거를 연결한다.

왜 구간을 나누는가: category_analyzer 는 앞·중간·뒤 표본만 본다(sample_input).
분류는 그것으로 충분하지만 **추출은 아니다** — 표본에 안 들어간 구간의 결정은
그냥 없어지고, 빠뜨린 것을 사람이 알아챌 방법도 없다. 그래서 summary_analyzer
처럼 전체를 덮는다.

왜 요약처럼 근거 인용을 요구하지 않는가: 결정사항은 사람이 승인하기 전까지
PENDING 제안으로만 남는다(DecisionScheduleWriter). 승인 화면이 곧 검증이므로
원문 대조를 파이프라인에서 강제하지 않는다. 대신 confidence 를 받아 정렬한다.

⚠️ 일정은 이 방식을 쓰지 않는다. schedule_analyzer.py 를 보라 — 3B 모델이
   날짜 필드를 못 채워서 날짜 찾기를 파이썬으로 옮겼다.
"""
import re
from difflib import SequenceMatcher

from app.analyzers.output_schemas import DecisionsOutput
from app.schemas.extraction import DecisionExtraction
from app.analyzers.prompt_input import PromptBudget, split_document
from app.analyzers.prompts import DECISION_PROMPT_VERSION, build_decision_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings


class DecisionAnalyzer:
    prompt_version = DECISION_PROMPT_VERSION
    stage_label = "결정사항 추출"
    field = "decisions"

    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        budget = PromptBudget(self._settings)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        chunks = split_document(text, budget, build_decision_prompt,
            overlap=self._settings.AI_CHUNK_OVERLAP_CHARS, max_chunks=self._settings.AI_MAX_CHUNKS)

        found, seen, empty_chunks = [], {}, []
        for i, chunk in enumerate(chunks):
            stage = f"{self.stage_label} {i + 1}/{len(chunks)}"
            runner.progress(stage, i, len(chunks))
            parsed = await runner.call(
                build_decision_prompt(chunk.text, chunk.start, chunk.end),
                DecisionsOutput, stage=stage)
            if not parsed.decisions:
                empty_chunks.append(i + 1)
            for item in parsed.decisions:
                grounded = _ground_decision(item, chunk.text)
                if grounded is None:
                    continue
                item = grounded
                # 구간이 앞뒤로 겹치므로 경계의 결정은 두 번 나온다. 같은 결정을
                # 두 구간이 다르게 요약할 수 있어 제목만으로는 못 합친다 —
                # 날짜와 상태까지 같아야 같은 것으로 본다.
                key = (item.title.strip(), item.status, item.decided_on)
                at = seen.get(key)
                if at is None:
                    seen[key] = len(found)
                    found.append(item)
                elif (item.confidence or 0) > (found[at].confidence or 0):
                    # 경계에 걸친 항목은 문맥을 더 많이 본 쪽이 대개 확신이 높다.
                    found[at] = item
            runner.progress(stage, i + 1, len(chunks))

        return AnalyzeResult(
            result={self.field: [item.model_dump(mode="json") for item in found],
                    "chunk_count": len(chunks), "empty_chunks": empty_chunks,
                    "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=self.prompt_version,
            **runner.metadata())


def _ground_decision(item, source: str) -> DecisionExtraction | None:
    """모델 문구와 가장 가까운 실제 원문 문장을 찾아 근거 없는 결과를 버린다."""
    segments = [part.strip() for part in re.split(r"[\r\n]+|(?<=[.!?다함])\s+", source)
                if 8 <= len(part.strip()) <= 500]
    if not segments:
        return None
    query = " ".join(value for value in (item.title, item.content) if value)
    normalized_query = re.sub(r"\s+", "", query)
    evidence = item.evidence_text.strip() if item.evidence_text else None
    if evidence and re.sub(r"\s+", "", evidence) in re.sub(r"\s+", "", source):
        best, score = evidence, 1.0
    else:
        best, score = max(((segment, SequenceMatcher(None, normalized_query,
            re.sub(r"\s+", "", segment)).ratio()) for segment in segments), key=lambda pair: pair[1])
    if score < 0.2:
        return None
    original_title = item.title.strip()
    short_title = _compact_title(original_title)
    content = item.content.strip() if item.content else None
    if not content:
        content = original_title if original_title != short_title else best
    if not _is_actual_decision(item, short_title, content, best):
        return None
    return DecisionExtraction(title=short_title, content=content,
        evidence_text=best, status=item.status, decided_on=item.decided_on,
        confidence=item.confidence, reason=item.reason)


_NEGATIVE_REASON = re.compile(r"결정사항이?\s*아니|결정사항을\s*포함하지|추론하지|추가\s*정보")
_PLACEHOLDER = re.compile(r"^(?:\.{2,}|-|없음|해당\s*없음)$")
_DECIDED_RESULT = re.compile(
    r"(하기로\s*(?:결정|확정|합의)|(?:선정|승인|확정|의결|채택|지정|취소)(?:하였|했|됨|되었|함|한다는\s*결정)|"
    r"(?:낙찰자|담당자|업체|대상자)(?:로|으로)\s*(?:선정|확정))")
_PENDING_RESULT = re.compile(r"(?:결정|선정|승인|확정|합의)\s*(?:예정|검토\s*중|협의\s*중)")
_RULE_TEXT = re.compile(r"제\s*\d+\s*조|세부\s*기준|평가\s*기준|하여야\s*한다|할\s*수\s*있다|으로\s*정한다")


def _is_actual_decision(item, title: str, content: str, evidence: str) -> bool:
    """원문에 있는 규정과 실제로 내려진 결정을 구분한다."""
    reason = item.reason or ""
    if _NEGATIVE_REASON.search(reason) or _PLACEHOLDER.fullmatch(title.strip()):
        return False
    combined = " ".join((title, content, evidence))
    if item.status.value == "PENDING":
        return bool(_PENDING_RESULT.search(combined))
    if item.status.value == "REVERSED":
        return bool(re.search(r"(?:결정|승인|선정).{0,30}(?:취소|철회|번복)|(?:취소|철회|번복)(?:하였|했|됨|함)", combined))
    if _RULE_TEXT.search(evidence) and not _DECIDED_RESULT.search(evidence):
        return False
    return bool(_DECIDED_RESULT.search(combined))


def _compact_title(title: str) -> str:
    original = title.strip()
    title = re.sub(r"^[\s○●■□▶·ㆍ※\-\d.)(①-⑳]+", "", title).strip()
    title = re.sub(r"(하기로\s*(결정|확정)(함|했다)?|으로\s*결정(함|했다)?)\.?$", "", title).strip()
    if len(title) <= 70:
        return title or original
    cut = max(title.rfind(mark, 0, 70) for mark in (" ", ",", "·", ";"))
    return title[:cut if cut >= 25 else 70].rstrip(" ,·;") or original[:70]
