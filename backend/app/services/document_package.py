"""파일명에서 동일 사업 문서 묶음의 보수적인 힌트를 만든다."""
from pathlib import Path
import re

_ROLES = (
    (r"공고서|공고문|안내공고|재공고", "NOTICE"),
    (r"제안요청서|제안\s*요청서", "RFP"),
    (r"과업지시서|과업내용서|과업설명서", "STATEMENT_OF_WORK"),
    (r"평가기준|적격심사표|낙찰자\s*결정", "EVALUATION_CRITERIA"),
    (r"입찰지침서|입찰유의서", "BIDDING_GUIDELINE"),
    (r"내역서|원가계산서|예정공정표", "COST_OR_SCHEDULE"),
    (r"서식|양식|서약서|이행각서", "FORM_OR_TEMPLATE"),
    (r"계약서|합의서|특수조건|일반조건", "CONTRACT_OR_TERMS"),
    (r"규격서|상세규격서|용도설명서", "SPECIFICATION"),
)
_DECORATION = re.compile(
    r"(?:\[[^\]]*(?:공고|제안요청|과업|붙임|협상)[^\]]*\]|"
    r"\((?:재공고|공고|최종|수정|변환본|공고용)\)|"
    r"\b(?:최종본?|수정\d*|v\d+|공고용|재공고)\b)", re.I)
_ROLE_WORDS = re.compile("|".join(f"(?:{pattern})" for pattern, _ in _ROLES), re.I)


def infer_package(filename: str) -> tuple[str | None, str | None]:
    stem = Path(filename).stem
    role = next((role for pattern, role in _ROLES if re.search(pattern, stem, re.I)), None)
    value = _DECORATION.sub(" ", stem)
    value = _ROLE_WORDS.sub(" ", value)
    value = re.sub(r"^[\s\[\](){}._-]*(?:붙임\s*)?\d+(?:[-.]\d+)?[.)_-]*", " ", value)
    value = re.sub(r"[^0-9A-Za-z가-힣]+", "", value).lower()
    # '공고문.pdf'처럼 사업 식별자가 없는 이름끼리는 절대 자동으로 묶지 않는다.
    if len(value) < 8:
        return None, role
    return value[:500], role
