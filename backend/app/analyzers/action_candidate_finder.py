"""원문에서 '해야 할 일'의 후보만 찾는 규칙 계층."""
import re
from dataclasses import dataclass
from datetime import date

from app.analyzers.date_finder import find_dates

_ACTION = re.compile(r"(제출|작성|준비|신청|등록|첨부|확인|검토|보고|납품|제작|보완|회신|송부|기재|발급|예약|참석)")
_OBLIGATION = re.compile(r"(하여야|해야|할\s*것|바람|바랍니다|주시|요청|필수|기한|마감|이내|까지|예정입니다)")
_EXCLUDE = re.compile(r"(법\s*제\d+조|조례\s*제\d+조|선정기준|심사기준|자격요건|자격조건|평가기준|제출서류\s*:|입찰무효|불이익|참가자격이\s*없|제재)")
_AUTHORITY = re.compile(r"^\s*(화성시|시장|심사위원|위원회|발주처|감독관)")
_BROKEN = re.compile(r"^\s*(사용하고|하고|하며|하여|제출하고)")
_NON_DELIVERABLE = re.compile(r"(?:숙지.{0,20}준수|단순\s*열람|요청할\s*수\s*있|제출을\s*요청할\s*수)")
_SCHEDULE_ONLY = re.compile(r"^\s*(?:납품|제출|접수|계약|사업)?\s*(?:기한|기간|일시)\s*[:：]")
_BULLET = re.compile(r"^[\s○●■□▶·ㆍ※\-\d.)(①-⑳]+")
_ACTOR = re.compile(r"(?:^|[\s(])(신청인|신청자|입찰참가자|입찰자|낙찰자|협력업체|계약상대자|계약자|수급인|수행기관|연구수행자|제안사|대표자|담당자)(?:은|는|이|가|에게|에서)?")
_GENERIC_RULE_DOC = re.compile(r"(?:행정안전부\s*예규|계약\s*일반조건|입찰\s*유의서|낙찰자\s*결정\s*기준)")
_PROPOSAL_DOC = re.compile(r"(?:기술|상품|사업|공급)?\s*제안서")
_ADOPTED = re.compile(r"(?:채택|승인|선정|합의|계약에\s*반영|이행하기로)")
_RELATIVE = re.compile(r"((?:계약|착수|통보|요청|선정|납품)일(?:로부터|부터)?\s*\d{1,3}\s*(?:영업일|일|주|개월|달)\s*(?:이내|안에|까지)?)")


@dataclass(frozen=True)
class ActionCandidate:
    id: str
    text: str
    title: str
    due_on: date | None
    actor: str | None
    quality_score: float
    section_type: str = "body"
    is_aggregate: bool = False
    statement_type: str = "OBLIGATION"
    actor_scope: str = "PROJECT_PARTY"
    modality: str = "MUST"
    task_kind: str = "ACTION"
    relative_expression: str | None = None
    condition: str | None = None

    def as_prompt_record(self):
        return {"id": self.id, "text": self.text,
                "due_on": self.due_on.isoformat() if self.due_on else None,
                "section_type": self.section_type,
                "is_aggregate": self.is_aggregate,
                "statement_type": self.statement_type,
                "actor_scope": self.actor_scope,
                "modality": self.modality,
                "task_kind": self.task_kind,
                "relative_expression": self.relative_expression,
                "condition": self.condition,
                "quality_score": self.quality_score}


def _task_kind(text: str) -> str:
    if re.search(r"제출|송부|회신|신청|등록", text):
        return "SUBMISSION"
    if re.search(r"보고", text):
        return "REPORTING"
    if re.search(r"납품|제작", text):
        return "DELIVERABLE"
    if re.search(r"검토|확인|보완", text):
        return "REVIEW"
    if re.search(r"참석|예약", text):
        return "ATTENDANCE"
    return "ACTION"


def _semantic_metadata(text: str, section_type: str, *, generic_rule: bool,
                       proposal: bool) -> dict:
    if section_type in {"form_or_appendix", "writing_guide"}:
        statement_type = "FORM_REQUIREMENT"
    elif proposal and not _ADOPTED.search(text):
        statement_type = "PROPOSAL_COMMITMENT"
    else:
        statement_type = "OBLIGATION"
    relative = _RELATIVE.search(text)
    condition = None
    conditional = re.search(r"([^.!?\n]{0,120}(?:경우|요청\s*시|필요\s*시)[^.!?\n]{0,160})", text)
    if conditional:
        condition = re.sub(r"\s+", " ", conditional.group(1)).strip()
    return {
        "statement_type": statement_type,
        "actor_scope": "GENERIC_RULE" if generic_rule else "PROJECT_PARTY",
        "modality": "CONDITIONAL" if condition else "MUST",
        "task_kind": _task_kind(text),
        "relative_expression": relative.group(1) if relative else None,
        "condition": condition,
    }


def _title(text: str) -> str:
    value = _BULLET.sub("", text).strip()
    if "PDF" in value and "이메일" in value and "제출" in value:
        return "제출서류 PDF 스캔 및 담당자 이메일 제출"
    if "나라장터" in value and "제안서" in value and "제출" in value:
        return "제안서 및 증빙서류 나라장터 제출"
    if "서약서" in value and "확인서" in value and "제출" in value:
        return "서약서 및 확인서 제출"
    if "과업수행계획서" in value and "제반서류" in value and "제출" in value:
        return "과업수행계획서와 제반서류 제출"
    value = re.sub(r"[.:]​?\s*$", "", value)
    value = re.sub(r"(하여야\s*합니다|해야\s*합니다|하여야\s*한다|해야\s*한다|하여야\s*함|해야\s*함|할\s*것입니다|할\s*것|바랍니다)\.?$", "", value)
    # 카드 제목은 한눈에 읽히는 실행명이어야 한다. 조건·근거 전문은 별도 필드에 둔다.
    value = re.split(r"(?:하여야|해야|바랍니다|주시기|주시면|할\s*것)", value, maxsplit=1)[0].strip()
    if len(value) > 90:
        action = list(_ACTION.finditer(value))
        if action:
            value = value[max(0, action[-1].start() - 65):action[-1].end()]
            value = re.sub(r"^\S+\s+", "", value) if len(value) > 70 else value
    return value[:90].rstrip(" ,·;:").strip()


def _actor(text: str) -> str | None:
    found = _ACTOR.search(text)
    return found.group(1) if found else None


def _join_wrapped_lines(text: str) -> str:
    """PDF/HWP가 한 문장을 줄 중간에서 끊은 경우만 보수적으로 이어 붙인다."""
    text = re.sub(
        r"(하여|하고|하며|하거나|거나|또는|및|후|송부하여|제출하여)\s*[\r\n]+\s*",
        r"\1 ", text)
    text = re.sub(r"[\r\n]+\s*(주시|하여야|해야|바랍니다)", r" \1", text)
    lines = [line.strip() for line in text.splitlines()]
    merged: list[str] = []
    for line in lines:
        if not line:
            continue
        if not merged:
            merged.append(line)
            continue
        previous = merged[-1]
        new_block = bool(re.match(r"[○●■□▶·ㆍ※①-⑳]|\d+[.)]\s", line))
        previous_is_heading = (len(previous) <= 80 and re.search(
            r"(?:제안서|요청서|공고서|계약서|과업지시서|보고서)$", previous))
        previous_is_schedule = bool(_SCHEDULE_ONLY.search(previous))
        complete = bool(re.search(r"[.!?]|(?:한다|합니다|하여야\s*함|해야\s*함)$", previous))
        if not new_block and not previous_is_heading and not previous_is_schedule and not complete:
            merged[-1] = previous + " " + line
        else:
            merged.append(line)
    return "\n".join(merged)


def find_action_candidates(text: str, limit: int = 60) -> list[ActionCandidate]:
    # 별지·부록을 통째로 버리지 않는다. 계약서 별지 작업지시서처럼
    # 실제 업무가 들어 있을 수 있으므로 구조 태그만 붙여 모델이 판단하게 한다.
    scan_text = _join_wrapped_lines(text)
    document_prefix = re.sub(r"\s+", " ", scan_text[:1600])
    first_line = next((re.sub(r"\s+", " ", line).strip()
                       for line in scan_text.splitlines() if line.strip()), "")
    generic_rule = bool(_GENERIC_RULE_DOC.search(document_prefix))
    proposal = bool(len(first_line) <= 100 and _PROPOSAL_DOC.search(first_line)
                    and re.search(r"제안서(?:\s*[-–—:].*)?$", first_line)
                    and not re.search(r"제안\s*요청서|입찰\s*공고", first_line))
    form_markers = [m.start() for m in re.finditer(r"\[별지\s*제?\s*1호\s*서식\]", scan_text)]
    form_start = min(form_markers) if form_markers else len(scan_text)
    guide = re.search(r"공적조서\s*및\s*구비서류\s*작성시\s*유의사항", scan_text[:form_start])
    parts = re.split(r"[\r\n]+|(?<=[.!?])\s+", scan_text)
    found, seen = [], set()

    # 접수 블록은 표 형태라 행단위 규칙으로는 '방문접수'만 남는다.
    receipt = re.search(r"접수기간\s*:(.{0,260}?)접수장소", scan_text, re.S)
    if receipt and re.search(r"접수방법\s*:\s*방문접수", receipt.group(0)):
        evidence = re.sub(r"\s+", " ", receipt.group(0)).strip()
        found.append(ActionCandidate("a1", evidence, "신청 서류 방문 제출", None,
                                     "신청인", 0.9, "body", False,
                                     **_semantic_metadata(evidence, "body",
                                         generic_rule=generic_rule, proposal=proposal)))
        seen.add("신청서류방문제출")
    cursor = 0
    for raw in parts:
        position = scan_text.find(raw, cursor) if raw else cursor
        if position >= 0:
            cursor = position + len(raw)
        value = re.sub(r"\s+", " ", raw).strip()
        if receipt and position >= 0 and position < receipt.end():
            # 접수 블록은 위에서 하나의 구조화 후보로 이미 만들었다.
            continue
        if not 10 <= len(value) <= 600 or not _ACTION.search(value):
            continue
        # 「납품기한: 2026/12/10」은 일정이지 독립된 업무가 아니다. 실제 납품·
        # 제출 의무 문장이 별도로 있을 때만 태스크 후보가 된다.
        if _SCHEDULE_ONLY.search(value):
            continue
        if (_EXCLUDE.search(value) or _AUTHORITY.search(value)
                or _BROKEN.search(value) or _NON_DELIVERABLE.search(value)):
            continue
        # 단순히 서류명을 나열한 행보다 의무·기한이 표시된 행을 우선한다.
        if not (_OBLIGATION.search(value) or re.search(r"(제출서류|접수방법|신청방법)", value)):
            continue
        title = _title(value)
        key = re.sub(r"[^0-9A-Za-z가-힣]", "", title)
        if not title or key in seen:
            continue
        seen.add(key)
        dates = find_dates(value)
        due = dates[-1].value if dates else None
        # 과거 예시 날짜를 현재 태스크 마감으로 넘기지 않는다.
        if due and due < date.today():
            due = None
        if position >= form_start:
            section_type = "form_or_appendix"
        elif guide and position + len(raw) >= guide.start():
            section_type = "writing_guide"
        else:
            section_type = "body"
        if re.search(r"(홍\s*길\s*동|00공방|ex\)|작성\s*예시)", value, re.I):
            section_type = "example"
        score = 0.55 + (0.2 if due else 0) + (0.15 if _OBLIGATION.search(value) else 0)
        if section_type == "form_or_appendix":
            score -= 0.2
        elif section_type == "example":
            score -= 0.35
        found.append(ActionCandidate(f"a{len(found)+1}", value, title, due, _actor(value),
                                     max(0.1, min(score, 1.0)), section_type, False,
                                     **_semantic_metadata(value, section_type,
                                         generic_rule=generic_rule, proposal=proposal)))
        if len(found) >= limit:
            break
    if guide:
        guide_text = re.sub(r"\s+", " ", scan_text[guide.start():form_start]).strip()
        evidence = guide_text[:1200]
        found.append(ActionCandidate(f"a{len(found)+1}", evidence,
            "필수 신청서류 작성 및 증빙자료 준비", None,
            "신청인", 0.9, "writing_guide", True,
            **_semantic_metadata(evidence, "writing_guide",
                generic_rule=generic_rule, proposal=proposal)))
    return found[:limit]
