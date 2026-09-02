"""원문에서 '해야 할 일'의 후보만 찾는 규칙 계층."""
import re
from dataclasses import dataclass
from datetime import date

from app.analyzers.date_finder import find_dates

_ACTION = re.compile(r"(제출|작성|준비|신청|등록|첨부|확인|검토|보고|납품|제작|보완|회신|송부|기재|발급|예약|참석)")
_OBLIGATION = re.compile(r"(하여야|해야|할\s*것|바람|필수|기한|마감|이내|까지)")
_EXCLUDE = re.compile(r"(법\s*제\d+조|조례\s*제\d+조|선정기준|심사기준|자격요건|자격조건|평가기준|제출서류\s*:)")
_AUTHORITY = re.compile(r"^\s*(화성시|시장|심사위원|위원회|발주처|감독관)")
_BROKEN = re.compile(r"^\s*(사용하고|하고|하며|하여|제출하고)")
_BULLET = re.compile(r"^[\s○●■□▶·ㆍ※\-\d.)(①-⑳]+")


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

    def as_prompt_record(self):
        return {"id": self.id, "text": self.text,
                "due_on": self.due_on.isoformat() if self.due_on else None,
                "section_type": self.section_type,
                "is_aggregate": self.is_aggregate,
                "quality_score": self.quality_score}


def _title(text: str) -> str:
    value = _BULLET.sub("", text).strip()
    if "PDF" in value and "이메일" in value and "제출" in value:
        return "제출서류 PDF 스캔 및 담당자 이메일 제출"
    value = re.sub(r"[.:]​?\s*$", "", value)
    value = re.sub(r"(하여야\s*합니다|해야\s*합니다|하여야\s*한다|해야\s*한다|하여야\s*함|해야\s*함|할\s*것입니다|할\s*것|바랍니다)\.?$", "", value)
    return value[:300].strip()


def find_action_candidates(text: str, limit: int = 60) -> list[ActionCandidate]:
    # 별지·부록을 통째로 버리지 않는다. 계약서 별지 작업지시서처럼
    # 실제 업무가 들어 있을 수 있으므로 구조 태그만 붙여 모델이 판단하게 한다.
    form_markers = [m.start() for m in re.finditer(r"\[별지\s*제?\s*1호\s*서식\]", text)]
    form_start = min(form_markers) if form_markers else len(text)
    guide = re.search(r"공적조서\s*및\s*구비서류\s*작성시\s*유의사항", text[:form_start])
    parts = re.split(r"[\r\n]+|(?<=[.!?])\s+", text)
    found, seen = [], set()

    # 접수 블록은 표 형태라 행단위 규칙으로는 '방문접수'만 남는다.
    receipt = re.search(r"접수기간\s*:(.{0,260}?)접수장소", text, re.S)
    if receipt and re.search(r"접수방법\s*:\s*방문접수", receipt.group(0)):
        evidence = re.sub(r"\s+", " ", receipt.group(0)).strip()
        found.append(ActionCandidate("a1", evidence, "신청 서류 방문 제출", None,
                                     "신청인", 0.9, "body"))
        seen.add("신청서류방문제출")
    cursor = 0
    for raw in parts:
        position = text.find(raw, cursor) if raw else cursor
        if position >= 0:
            cursor = position + len(raw)
        value = re.sub(r"\s+", " ", raw).strip()
        if not 10 <= len(value) <= 600 or not _ACTION.search(value):
            continue
        if _EXCLUDE.search(value) or _AUTHORITY.search(value) or _BROKEN.search(value):
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
        elif guide and position >= guide.start():
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
        found.append(ActionCandidate(f"a{len(found)+1}", value, title, due, None,
                                     max(0.1, min(score, 1.0)), section_type))
        if len(found) >= limit:
            break
    if guide:
        guide_text = re.sub(r"\s+", " ", text[guide.start():form_start]).strip()
        evidence = guide_text[:1200]
        found.append(ActionCandidate(f"a{len(found)+1}", evidence,
            "필수 신청서류 작성 및 증빙자료 준비", None,
            "신청인", 0.9, "writing_guide", True))
    return found[:limit]
