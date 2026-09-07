# =============================================================================
# 이 파일의 책임: 금액 검산 불일치를 **승인형 태스크 제안**으로 만든다
#   (AMT-004-3 불일치 태스크 제안 · TSK-002-1 AI 제안 승인).
# 다른 파일과의 관계: AmountRepository 로 항목을 읽고 amount_calculator 로 다시
#   검산한 뒤 TaskService.create 로 태스크를 만든다. TaskRepository 는 같은
#   항목으로 이미 만든 태스크가 있는지 보는 데만 쓴다.
# Spring 비교: 두 도메인(금액·태스크)을 잇는 응용 서비스다. 각 도메인 서비스를
#   호출만 하고 자기 저장소를 갖지 않는 @Service 에 해당한다.
#
# 제안을 저장하지 않는다
#   불일치는 **결정론적으로 다시 계산된다.** amount-summary 를 부를 때마다 새로
#   만들어지므로 테이블에 또 넣을 이유가 없다. 그래서 이 기능에는 마이그레이션이
#   없다.
#
#   LLM 이 뽑은 제안(ANL-002-1)은 다르다 — 호출 비용이 들고 결과가 매번 달라서
#   다시 계산할 수 없다. 그때는 저장할 테이블이 필요하다. **「다시 계산할 수 있는가」
#   가 저장 여부를 가르는 기준이다.**
#
# 자동으로 만들지 않는다
#   AMT-004-3 완료 판정이 "승인형 태스크 제안 카드가 생기고 **자동 등록은 하지
#   않는다**" 다. 그래서 검산할 때 태스크를 만들지 않고, 사람이 누를 때만 만든다.
#   TSK-002-1 의 "승인 전에는 보드에 나타나지 않는다" 도 같이 만족한다 — 승인
#   전에는 tasks 에 행이 아예 없으므로 보드 조회를 건드릴 필요가 없다.
#
# 화면이 보낸 값을 믿지 않는다
#   요청 본문에 금액이나 차액을 받지 않는다. 항목 id 만 받아 **서버가 다시 검산**
#   한다. 화면이 낡은 목록을 들고 있으면 이미 고쳐진 항목으로 태스크를 만들 수
#   있고, 그러면 근거 없는 태스크가 남는다.
# =============================================================================

from __future__ import annotations

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.models.amount import AmountItem
from app.models.task import Task
from app.repositories.amount_repository import AmountRepository
from app.repositories.task_repository import TaskRepository
from app.services.amount_calculator import verify_line
from app.services.amount_summary_service import AmountSummaryService
from app.services.task_service import TaskService

# 태스크 제목은 300자 제한이다(tasks.title). 항목명이 길면 잘라서 넣는다.
_TITLE_PREFIX = "금액 불일치: "
_TITLE_LIMIT = 300


class AmountTaskService:
    def __init__(
        self,
        amounts: AmountRepository,
        tasks: TaskRepository,
        task_service: TaskService,
    ) -> None:
        self._amounts = amounts
        self._tasks = tasks
        self._task_service = task_service

    def create_from_mismatch(
        self, project_id: int, item_id: int, user_id: int
    ) -> Task:
        """불일치 항목 하나를 태스크로 만든다 (AMT-004-3).

        막는 경우가 셋이고 **오류 코드를 다르게 준다.** 화면이 해야 할 일이 다르다.

        | 언제 | 코드 | 화면이 할 일 |
        |---|---|---|
        | 그 항목이 없다(다른 프로젝트 것 포함) | `404 AMOUNT_ITEM_NOT_FOUND` | 목록을 다시 받는다 |
        | 어긋난 항목이 아니다 | `409 AMOUNT_NOT_MISMATCHED` | 목록이 낡았다 — 다시 받는다 |
        | 이미 만든 태스크가 있다 | `409 AMOUNT_TASK_ALREADY_EXISTS` | 그 태스크를 가리킨다 |

        검산 불가(수량·단가가 없는 제경비 등)와 금액이 안 적힌 항목도
        `AMOUNT_NOT_MISMATCHED` 다 — **어긋난 것이 아니기 때문**이다. 오류가 아니라
        정상 항목이라서 태스크로 만들 이유가 없다.
        """
        found = self._amounts.get_item(project_id, item_id)
        if found is None:
            raise BusinessError(ErrorCode.AMOUNT_ITEM_NOT_FOUND)
        item, document_id, filename = found

        check = self._verify(item, document_id, filename)
        # matches 가 True(맞음)거나 None(검산 불가)이면 만들지 않는다.
        if check is None or check.matches is not False:
            raise BusinessError(ErrorCode.AMOUNT_NOT_MISMATCHED)

        existing = self._tasks.suggestion_task_ids(project_id).get(item.id)
        if existing is not None:
            # 같은 불일치로 태스크가 둘 생기면 보드에서 같은 일이 두 번 보인다.
            raise BusinessError(ErrorCode.AMOUNT_TASK_ALREADY_EXISTS)

        return self._task_service.create(
            project_id,
            user_id,
            {
                "title": self._title(item.item_name),
                "description": self._description(
                    item, filename, check.expected or 0, check.difference or 0
                ),
                # 문서에 적힌 값을 확인하는 일이라 DOCUMENT 로 둔다. 개발·설계·인프라
                # 어디에도 속하지 않고, OTHER 로 두면 보드에서 성격을 알 수 없다.
                "type": "DOCUMENT",
            },
            origin="AI_APPROVED",
            source_amount_item_id=item.id,
        )

    # --- 내부 ---------------------------------------------------------------

    @staticmethod
    def _verify(item: AmountItem, document_id: int, filename: str):
        """항목 하나를 다시 검산한다. 금액이 안 적혀 있으면 검산 자체가 안 된다.

        `AmountSummaryService._to_line` 을 재사용한다. 변환 규칙(Enum·반올림·
        None 처리)이 두 곳에 생기면 합계 화면과 이 판정이 어긋난다.
        """
        if item.amount is None:
            return None
        return verify_line(
            AmountSummaryService._to_line(item, document_id, filename)
        )

    @staticmethod
    def _title(item_name: str) -> str:
        room = _TITLE_LIMIT - len(_TITLE_PREFIX)
        name = item_name.strip()
        if len(name) > room:
            # 자른 표시를 남긴다. 말없이 자르면 항목명이 원래 그런 줄 안다.
            name = name[: room - 1] + "…"
        return _TITLE_PREFIX + name

    @staticmethod
    def _description(
        item: AmountItem, filename: str, expected: int, difference: int
    ) -> str:
        """태스크 설명을 **서버가 만든다.**

        화면마다 문구를 만들면 같은 태스크가 다르게 적힌다. 그리고 이 문구는
        보드·산출물 등 금액 화면이 아닌 곳에서도 읽히므로, 그 자리에 계산 근거가
        함께 있어야 무슨 일인지 알 수 있다.

        부호를 그대로 쓰지 않는다 — `difference` 는 `계산값 − 문서 금액` 이라
        문서 금액이 크면 음수다. `-50,000` 만 적으면 "부족" 으로 읽힌다.
        """
        gap = (
            f"문서 금액이 {abs(difference):,}원 "
            + ("적습니다" if difference > 0 else "많습니다")
        )
        lines = [
            f"출처 문서: {filename}",
            f"항목: {item.item_name}",
            f"수량 × 단가: {item.quantity} {item.unit or ''} × {item.unit_price:,}원 = {expected:,}원".replace(
                "  ", " "
            ),
            f"문서에 적힌 금액: {int(item.amount):,}원",
            f"차이: {gap}",
            "",
            "수량·단가와 문서에 적힌 금액 중 어느 쪽이 맞는지 확인해 주세요.",
            "금액 탭 → 항목 보기에서 이 항목을 고치면 합계와 검산에 바로 반영됩니다.",
        ]
        return "\n".join(lines)
