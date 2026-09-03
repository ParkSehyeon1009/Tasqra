import re

from app.analyzers.output_schemas import CategoryOutput
from app.analyzers.prompt_input import PromptBudget, sample_input
from app.analyzers.prompts import CATEGORY_PROMPT_VERSION, build_category_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings


class CategoryAnalyzer:
    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        budget = PromptBudget(self._settings)
        prompt, meta = sample_input(text, budget, build_category_prompt)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        runner.progress("문서 분류", 0, 1)
        parsed = await runner.call(prompt, CategoryOutput, stage="문서 분류")
        category, reason = _validate_category(text, parsed.category, parsed.reason)
        traits = _document_traits(text)
        family = _document_family(text)
        document_state = _document_state(text)
        runner.progress("문서 분류", 1, 1)
        return AnalyzeResult(
            result={"category": category, "reason": reason, "family": family,
                    "document_state": document_state, "traits": traits,
                    "input_scope": meta, "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=CATEGORY_PROMPT_VERSION,
            **runner.metadata(),
        )


def _validate_category(text: str, category: str, reason: str) -> tuple[str, str]:
    """제목·문서 목적과 명백히 모순되는 단일 분류만 보수적으로 교정한다."""
    compact = re.sub(r"\s+", "", text[:1200])
    if re.search(r"(?:구매|용역|공사)?입찰(?:재)?공고|제안요청서", compact, re.I):
        if category != "RFP":
            return "RFP", "문서 제목과 도입부에 입찰 공고 또는 제안요청서가 명시되어 있음"
    if re.search(r"(?:협력방안|상품공급|사업)제안서", compact) and not re.search(r"입찰(?:재)?공고", compact):
        if category == "ETC":
            return "PROPOSAL", "문서 제목과 도입부의 주된 목적이 협력 또는 상품 공급 제안임"
    if category == "COST_SHEET":
        return "ETC", "산출내역서·견적서·원가계산서는 7종 분류 정책에서 기타로 통합됨"
    return category, reason


def _document_traits(text: str) -> list[str]:
    """주 유형과 별개로 후속 기능에 유용한 복합 성격만 보수적으로 표시한다."""
    compact = re.sub(r"\s+", "", text)
    rules = (
        ("COST_DETAILS", r"산출내역서|원가계산서|견적서|수량\s*단가\s*(?:금액|합계)|공급가액.*부가세"),
        ("SCHEDULE", r"추진일정|사업기간|계약기간|제출기한|접수기간|일정표"),
        ("CONTRACT_TERMS", r"계약조건|계약금액|계약기간|과업내용|지체상금|하자보수"),
        ("DECISION_RECORD", r"의결사항|결정사항|합의사항|승인결과|선정결과"),
        ("ACTION_ITEMS", r"조치사항|후속조치|담당자.*기한|까지\s*(?:제출|보고|완료|회신)"),
        ("REQUIREMENTS", r"요구사항|필수\s*요건|성능\s*요건|상세\s*규격|규격서"),
        ("EVALUATION_RULES", r"평가\s*기준|배점|평가항목|낙찰자\s*결정|협상대상자"),
        ("FORM_FIELDS", r"별지\s*제?\s*\d+호\s*서식|신청인.*\(인\)|작성\s*방법"),
        ("PAYMENT_TERMS", r"대가\s*지급|지급\s*조건|청구액|노무비|선금"),
        ("ACCEPTANCE_CRITERIA", r"검사|검수|시험\s*기준|합격\s*기준|하자"),
        ("RELATIVE_DEADLINES", r"(?:계약|착수|통보|요청)일(?:로부터|부터).{0,30}(?:이내|동안|까지)"),
        ("PROPOSAL_COMMITMENTS", r"제안.{0,40}(?:하겠습니다|지원\s*가능|제공\s*예정|수행\s*예정)"),
    )
    return [name for name, pattern in rules if re.search(pattern, compact, re.I)]


def _document_family(text: str) -> str:
    """화면의 기존 7종 분류와 별개인 세부 역할. 새 유형도 의미 특성으로 보완한다."""
    prefix = re.sub(r"\s+", "", text[:1800])
    rules = (
        (r"(?:입찰|견적)(?:재)?공고|안내공고", "NOTICE"),
        (r"제안요청서", "RFP"),
        (r"과업(?:지시|내용|설명)서", "STATEMENT_OF_WORK"),
        (r"평가기준|낙찰자결정.*기준", "EVALUATION_CRITERIA"),
        (r"입찰지침서|입찰유의서|계약집행기준|일반조건|특수조건", "RULE_OR_GUIDELINE"),
        (r"(?:계약서|합의서|협약서)", "CONTRACT"),
        (r"(?:신청서|청구서|서약서|이행각서|제출서류양식)", "FORM_OR_TEMPLATE"),
        (r"(?:산출|공|설계|물량|예산)내역서|원가계산서", "COST_SHEET"),
        (r"예정공정표|추진일정표", "SCHEDULE_SHEET"),
        (r"규격서|상세규격|용도설명서", "SPECIFICATION"),
        (r"(?:완료|착수|주간|월간)보고서|검사조서", "REPORT"),
        (r"인증서|CERTIFICATE", "CERTIFICATE"),
        (r"제안서", "PROPOSAL"),
    )
    return next((family for pattern, family in rules if re.search(pattern, prefix, re.I)), "OTHER")


def _document_state(text: str) -> str:
    compact = re.sub(r"\s+", "", text[:3000])
    if re.search(r"초안|\(안\)|DRAFT", compact, re.I):
        return "DRAFT"
    if re.search(r"체결하였|합의하였|서명완료|계약일자\s*:\s*20\d{2}", compact):
        return "EXECUTED"
    # 공고문 뒤에 첨부 서식이 있다는 이유만으로 문서 전체를 양식으로 보지 않는다.
    if (_document_family(text) == "FORM_OR_TEMPLATE" or
            re.search(r"^(?:.{0,100})(?:작성예시|제출서류양식|별지제?\d+호서식)", compact)):
        return "TEMPLATE"
    return "PUBLISHED"
