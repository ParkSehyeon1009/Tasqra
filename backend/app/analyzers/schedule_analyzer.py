"""일정 추출. 날짜는 파이썬이 찾고 모델은 무엇의 날짜인지만 고른다.

왜 이렇게 나눴는가 (실측):

    모델에게 전부 시켰을 때        날짜가 채워진 항목 0/4
    필드를 원문 문자열로 바꿨을 때  날짜가 채워진 항목 0/3
    정규식으로 찾았을 때            10/10, 문맥까지 온전

3B 모델은 날짜를 제목에 적고 날짜 필드를 비워둔다. 형식 변환 문제가 아니라
필드를 나눠 채우는 것 자체를 못 한다. 그래서 찾기를 넘겨받았다.

부수 효과가 크다 — 모델은 목록에 있는 id 만 고를 수 있으므로 **없는 날짜를
만들 수 없다.** 요약의 evidence_ids 와 같은 방식이다.
"""
import re

from app.analyzers.date_finder import find_dates
from app.analyzers.output_schemas import DatedItemsOutput
from app.analyzers.prompt_input import PromptBudget
from app.analyzers.prompts import SCHEDULE_PROMPT_VERSION, build_schedule_prompt
from app.analyzers.protocol import AnalyzeResult
from app.analyzers.runner import Runner
from app.core.config import settings
from app.schemas.extraction import ScheduleItemExtraction, ScheduleKind


# 이름에서 종류를 읽는 규칙. **순서가 곧 우선순위다.**
#
# 왜 규칙인가: kind 는 화면 라벨이 아니라 **어느 날짜 컬럼이 의미를 갖는지**를
# 정한다(models/schedule.py 머리말). 틀리면 항목이 달력에서 조용히 사라진다.
# 그런데 모델은 여기서 오락가락한다 — 같은 문서를 두 번 돌리면 MILESTONE 과
# DEADLINE 이 바뀌고, 분류 모델은 아예 한 값으로 무너졌다.
#
# 공공 문서의 이름은 종류를 그 안에 담고 있다(「납품기한」·「제안서평가일시」).
# 기계가 읽을 수 있는 것을 모델에게 짐작시키지 않는다 — 날짜를 정규식으로
# 옮긴 것과 같은 이유다.
_KIND_RULES = (
    # 「기간」이 가장 강하다. 「제출기간」은 마감이 아니라 구간이다.
    (re.compile(r"기간"), ScheduleKind.PERIOD),
    # 끝나는 시점. 「평가위원질의종료일시」처럼 평가가 섞여 있어도 종료가 이긴다.
    (re.compile(r"기한|마감|종료|까지|납품일"), ScheduleKind.DEADLINE),
    # 모여서 하는 일. 「온라인평가 시작일시」는 평가가 시작을 이긴다.
    (re.compile(r"평가|개찰|회의|심사|발표|설명회|공개회|면담|협상"), ScheduleKind.MEETING),
    (re.compile(r"착수|개시|시작|준공|검수|선임|완료|체결"), ScheduleKind.MILESTONE),
)


def kind_from_label(label: str | None) -> ScheduleKind | None:
    """이름에서 종류를 읽는다. 못 읽으면 None — 그때는 모델의 판단을 쓴다."""
    if not label:
        return None
    for pattern, kind in _KIND_RULES:
        if pattern.search(label):
            return kind
    return None


class ScheduleAnalyzer:
    def __init__(self, ai_client, config=None):
        self._ai_client = ai_client
        self._settings = config or settings

    async def analyze(self, text: str, *, progress=None) -> AnalyzeResult:
        budget = PromptBudget(self._settings)
        runner = Runner(self._ai_client, self._settings, budget, progress)
        dates = find_dates(text)

        if not dates:
            # 날짜가 없는 문서다. 모델을 부를 이유가 없다 — 부르면 없는 일정을
            # 지어낼 기회만 준다. 호출 0회로 끝내되 그 사실을 남긴다.
            return AnalyzeResult(
                result={"schedule_items": [], "date_count": 0, "labeled_count": 0,
                        "call_count": 0},
                provider=self._ai_client.provider, prompt_version=SCHEDULE_PROMPT_VERSION,
                model_name=self._ai_client.model_name, latency_ms=0)

        groups = self._split_by_budget(dates, budget)
        items: list[ScheduleItemExtraction] = []
        labeled = 0
        for i, group in enumerate(groups):
            stage = f"일정 라벨링 {i + 1}/{len(groups)}" if len(groups) > 1 else "일정 라벨링"
            runner.progress(stage, i, len(groups))
            allowed = {found.id: found for found in group}

            def verify(parsed, allowed=allowed):
                for item in parsed.items:
                    if not set(item.date_ids) <= allowed.keys():
                        raise ValueError("unknown date id")
                    if len(set(item.date_ids)) != len(item.date_ids):
                        raise ValueError("duplicated date id")

            parsed = await runner.call(
                build_schedule_prompt([found.as_prompt_record() for found in group]),
                DatedItemsOutput, validate=verify, stage=stage)
            for item in parsed.items:
                built = self._build(item, allowed)
                if built is not None:
                    items.append(built)
                    labeled += len(item.date_ids)
            runner.progress(stage, i + 1, len(groups))

        # 원문 순서가 아니라 **날짜 순서**로 준다. 화면에서 그대로 일정이 된다.
        items.sort(key=lambda item: (item.starts_on or item.ends_on, item.title))
        return AnalyzeResult(
            result={"schedule_items": [item.model_dump(mode="json") for item in items],
                    # 찾은 날짜 중 몇 개가 일정이 됐는지. 이 비율이 낮으면
                    # 프롬프트가 문맥을 못 읽고 있다는 신호다.
                    "date_count": len(dates), "labeled_count": labeled,
                    "call_count": runner.calls},
            provider=self._ai_client.provider, prompt_version=SCHEDULE_PROMPT_VERSION,
            **runner.metadata())

    def _split_by_budget(self, dates, budget):
        """날짜가 많은 문서는 목록을 나눠 보낸다. 한 묶음이 예산을 넘지 않게."""
        groups, group = [], []
        for found in dates:
            candidate = group + [found]
            if group and not budget.fits(
                    build_schedule_prompt([f.as_prompt_record() for f in candidate])):
                groups.append(group)
                group = [found]
            else:
                group = candidate
        if group:
            groups.append(group)
        return groups

    @staticmethod
    def _title(item, picked_dates) -> str:
        """원문에서 이름을 떼어낼 수 있었으면 모델의 제목 대신 그것을 쓴다.

        모델은 이름을 자주 바꾼다 — 「제출시작일시」를 「제출 마감」으로 쓰면
        사람이 날짜를 착각한다. 정규식이 콜론 앞에서 잡아낸 이름은 원문 그대로라
        짐작이 섞이지 않는다. 잡히지 않는 문서(산문·표)에서만 모델 것을 쓴다.

        ⚠️ 힌트로 넘겨 모델이 쓰게 하는 방법은 시험했다가 접었다. 제목에 날짜를
          넣거나 한 가지 이름으로 무너졌다. 기계가 아는 것은 기계가 쓴다.
        """
        labels = [found.label for found in picked_dates if found.label]
        title = labels[0] if labels else item.title
        title = re.sub(r"\d{4}\s*[./년-]\s*\d{1,2}\s*[./월-]\s*\d{1,2}\s*일?", "", title)
        title = re.sub(r"\s+", " ", title).strip(" :-·")
        return title[:70].rstrip() or "일정"

    @staticmethod
    def _build(item, allowed) -> ScheduleItemExtraction | None:
        """고른 id 를 실제 날짜로 바꾼다. 모델이 아니라 여기서 날짜가 정해진다."""
        chosen = [allowed[i] for i in item.date_ids]
        title = ScheduleAnalyzer._title(item, chosen)
        picked = sorted(found.value for found in chosen)
        # 이름에서 종류를 읽을 수 있으면 그것이 이긴다. 못 읽을 때만 모델을 쓴다.
        labels = [found.label for found in chosen if found.label]
        kind = kind_from_label(labels[0] if labels else None) or item.kind

        if kind is ScheduleKind.PERIOD and picked[0] == picked[-1]:
            # 기간이라면서 시작과 끝이 같은 날이다. 하나만 골랐거나, 서로 다른
            # id 두 개가 **같은 날짜**를 가리킨 경우다(같은 날에 시작·종료
            # 시각이 따로 적힌 문서에서 실제로 나온다).
            #
            # ⚠️ 개수만 보면 안 된다. 그대로 담으면 달력이 그날 하루를 「기간」
            #   으로 칠하는데, 원문에 없던 뜻이다. 마감으로 낮춰 담는다.
            kind = ScheduleKind.DEADLINE

        if kind is ScheduleKind.PERIOD:
            return ScheduleItemExtraction(
                title=title, evidence_text=chosen[0].context.strip(),
                kind=kind, starts_on=picked[0], ends_on=picked[-1],
                confidence=item.confidence, reason=item.reason)

        # ⚠️ 한 시점을 **kind 가 지정하는 컬럼**에 담아야 한다. models/schedule.py
        #   머리말이 정한 규칙이다:
        #       MILESTONE · MEETING  starts_on 만 의미가 있다
        #       DEADLINE             ends_on 만 의미가 있다
        #   틀리면 조용히 사라진다. ScheduleItem.due_date 도 프런트의
        #   eventPrimaryDate() 도 kind 를 보고 컬럼을 고르므로, MEETING 을
        #   ends_on 에 담으면 **달력에 아예 뜨지 않는다.**
        #
        #   반대로 양쪽에 같은 날짜를 넣어 안전하게 가는 것도 안 된다. CHECK 는
        #   통과하지만 「하루짜리 기간」이라는 없던 뜻이 생긴다.
        when = picked[-1]        # 둘을 골랐으면 늦은 쪽을 그 시점으로 본다
        if kind is ScheduleKind.DEADLINE:
            starts_on, ends_on = None, when
        else:
            starts_on, ends_on = when, None
        return ScheduleItemExtraction(
            title=title, evidence_text=chosen[-1].context.strip(),
            kind=kind, starts_on=starts_on, ends_on=ends_on,
            confidence=item.confidence, reason=item.reason)
