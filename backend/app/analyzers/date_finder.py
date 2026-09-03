"""원문에서 날짜를 찾는다. LLM 을 쓰지 않는다.

왜 파이썬이 찾는가: 3B 모델은 날짜를 **제목에 적고 날짜 필드는 비워둔다.**
실측했다 — `date` 타입으로 강제해도, 원문 그대로 받는 문자열로 바꿔도
채워진 항목이 0/4 와 0/3 이었다. 형식 변환 문제가 아니라 필드를 나눠 채우는
것 자체를 못 한다.

정규식은 이 일을 완벽하게 한다. 조달청 재공고서에서 10개를 전부 찾았고,
추출기가 뱉는 `2026.   07.   20` 처럼 공백이 낀 것도 잡는다.

그래서 역할을 나눈다:
    파이썬  날짜를 찾는다          -> 누락도 환각도 없다
    모델    무엇의 날짜인지 고른다  -> 3B 가 잘하는 분류 문제
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

# 공공 문서에 실제로 나오는 형태. 추출기가 공백을 여러 칸 뱉으므로 사이를 허용한다.
_PATTERNS = (
    re.compile(r"(\d{4})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{1,2})"),
    re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
)
# 기간의 뒤쪽에서 연도(또는 연도·월)를 생략하는 공공문서 표기를 보완한다.
# 예: 2026. 8. 3. ~ 8. 31. / 2026. 7. 13. ~ 15.
_ABBREVIATED_RANGE = re.compile(
    r"(?P<year>\d{4})\s*[./\-]\s*(?P<month>\d{1,2})\s*[./\-]\s*(?P<day>\d{1,2})\s*\.?"
    + r"\s*(?:~|～|−|–|—|부터)\s*"
    + r"(?!\d{4}\s*[./\-])"
    + r"(?:(?P<end_month>\d{1,2})\s*[./\-]\s*)?(?P<end_day>\d{1,2})(?:\s*일)?"
)
# 앞쪽을 넉넉히 본다 — 「제안서평가일시: 2026/07/20」처럼 **날짜 앞에** 무슨
# 날짜인지가 적히기 때문이다. 뒤쪽은 시각과 「~까지」 정도만 필요하다.
BEFORE, AFTER = 120, 40

# 날짜 **바로 앞**의 「이름:」. 공공 서식은 이 모양이 지배적이다.
#     ○ 납품기한: 2026/12/10
#     ·  평가위원질의종료일시   :   2026.   07.   20.
# 모델은 이 이름을 자주 바꿔 쓴다(「제출시작일시」→「제출 마감」). 여기서 잡히면
# 그것이 정답이므로 모델에게 짐작시키지 않는다.
_LABEL = re.compile(
    r"(?:^|[\n○●◦·∙*■□▪▶〉>\-–—)])\s*"   # 글머리표·닫는 괄호 또는 줄 시작
    r"(?P<label>[^\n:：]{2,40}?)"           # 이름 (콜론·줄바꿈 없이 2~40자)
    r"\s*[:：]\s*$"                         # 콜론으로 끝난다
)
# 이름처럼 보이지만 아닌 것. 「1) 입찰의 일시 및 장소」 같은 목차 번호가 섞인다.
_NOT_LABEL = re.compile(r"[.。]\s|다\s*$|습니다|바랍니다")
_PERIOD_LABEL = re.compile(r"(?:^|[○●◦·∙*■□▪▶〉>\-–—)])\s*([^:：\n]{2,40}?기간)\s*[:：][^:：\n]{0,100}$")


def _label_before(context: str, raw: str, at: int | None = None) -> str | None:
    # 같은 날짜가 가까이 반복될 수 있으므로 문자열 검색보다 원문 위치를 우선한다.
    at = context.find(raw) if at is None else at
    if at < 0:
        return None
    found = _LABEL.search(context[:at])
    if not found:
        period = _PERIOD_LABEL.search(context[:at])
        if not period:
            return None
        label = re.sub(r"\s+", " ", period.group(1)).strip()
    else:
        label = re.sub(r"\s+", " ", found.group("label")).strip()
    # context 가 문장 중간에서 잘리면 글머리표가 앞에 남는다(「- 제출기한」).
    # 화면에 그대로 뜨므로 걷어낸다.
    label = re.sub(r"^[\s○●◦·∙*■□▪▶〉>\-–—.·]+", "", label).strip()
    # 문장이 딸려 들어오면 이름이 아니다. 짧게 잘라 쓰느니 모델에게 맡긴다.
    if not label or _NOT_LABEL.search(label):
        return None
    return label


@dataclass(frozen=True)
class FoundDate:
    id: str          # "d1" — 모델이 이 id 로만 날짜를 가리킬 수 있다
    at: int          # 원문 위치
    raw: str         # 원문에 적힌 그대로 ("2026.   07.   20")
    value: date
    context: str     # 앞뒤를 잘라낸 문맥
    label: str | None = None   # 콜론 앞에서 잡은 이름. 없으면 모델이 정한다
    context_type: str = "body"  # 예시·이력은 삭제하지 않고 판단 힌트만 준다
    range_key: int | None = None  # 원문에서 ~·부터/까지로 연결된 같은 기간

    def as_prompt_record(self) -> dict:
        # ⚠️ label 은 **모델에게 보내지 않는다.** 힌트로 줘 봤더니 오히려 나빠졌다
        #   (제목에 날짜를 넣거나, 한 가지 이름으로 무너졌다). 모델은 context 만
        #   보고 판단하게 두고, label 이 있으면 파이썬이 결과를 덮어쓴다.
        #   schedule_analyzer._build() 를 보라.
        return {"id": self.id, "date": self.value.isoformat(), "context": self.context,
                "context_type": self.context_type,
                "range_id": f"r{self.range_key}" if self.range_key is not None else None}


def _context_type(context: str) -> str:
    if re.search(r"홍\s*길\s*동|작성\s*예시|기재\s*예시|예\s*\)", context, re.I):
        return "example"
    if re.search(r"경력|이력|과거|발급일자|심사위원\s*참여", context):
        return "history_or_form"
    return "body"


def find_dates(text: str, *, limit: int = 60) -> list[FoundDate]:
    """원문 순서대로 날짜를 준다. 겹치는 match 는 앞선 것만 남긴다.

    ⚠️ limit 을 두는 이유: 표·이력이 많은 문서는 날짜가 수백 개 나온다. 그대로
    프롬프트에 실으면 예산을 넘긴다. 넘치면 **앞에서부터** 자른다 — 공고문·
    과업지시서는 중요한 일정이 앞에 모여 있다.
    """
    matches = []
    for pattern in _PATTERNS:
        for found in pattern.finditer(text):
            year, month, day = (int(g) for g in found.groups())
            try:
                value = date(year, month, day)
            except ValueError:
                continue          # 2026/13/45 같은 것은 날짜가 아니다
            matches.append((found.start(), found.end(), found.group(0), value))

    for found in _ABBREVIATED_RANGE.finditer(text):
        year = int(found.group("year"))
        month = int(found.group("end_month") or found.group("month"))
        day = int(found.group("end_day"))
        try:
            value = date(year, month, day)
        except ValueError:
            continue
        start, end = found.span("end_day")
        matches.append((start, end, text[start:end], value))

    matches.sort()
    dates: list[FoundDate] = []
    last_end = -1
    for start, end, raw, value in matches:
        if start < last_end:
            continue              # 앞선 match 와 겹친다
        last_end = end
        context_start = max(0, start - BEFORE)
        context = text[context_start:end + AFTER].replace("\n", " ")
        dates.append(FoundDate(f"d{len(dates) + 1}", start, raw, value, context,
                               _label_before(context, raw, start - context_start),
                               _context_type(context)))
        if len(dates) >= limit:
            break
    for index in range(1, len(dates)):
        previous, current = dates[index - 1], dates[index]
        between = text[previous.at + len(previous.raw):current.at]
        if len(between) <= 100 and re.search(r"(?:~|～|−|–|—|부터)", between):
            key = previous.range_key if previous.range_key is not None else previous.at
            label = current.label or previous.label
            dates[index - 1] = replace(previous, range_key=key)
            dates[index] = replace(current, label=label, range_key=key)
    return dates
