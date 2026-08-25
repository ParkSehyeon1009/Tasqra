# =============================================================================
# 이 파일의 책임: 금액 항목을 사람이 고치는 것 (AMT-001-2 금액 항목 승인·수정).
#   고치면 decision 이 EDITED 가 되고 누가 언제 고쳤는지 남는다.
# 다른 파일과의 관계: AmountRepository 로 항목을 읽고 그 자리에서 고친다. 응답은
#   AmountSummaryService._to_row 를 재사용해 만든다 — 목록과 같은 모양이어야
#   화면이 고친 줄만 갈아끼울 수 있다. TaskRepository 는 task_id 를 붙이는 데만 쓴다.
# Spring 비교: @Service + @Transactional 이다. transactional(db) 컨텍스트매니저가
#   그 어노테이션 자리를 대신한다.
#
# 왜 이 파일이 필요했나 — 없는 기능을 가리키고 있었다
#   금액 불일치 태스크(AMT-004-3)의 설명에 "값을 고치면 불일치 표시가 사라집니다"
#   라고 적어 뒀는데 **고칠 API 가 없었다.** decision='EDITED' 는 스키마와 주석에만
#   있고 그 상태로 바꾸는 코드가 어디에도 없었다. 설계에 있는 것과 만들어진 것을
#   구분하지 못한 실수였다.
#
# 검산 결과를 여기서 저장하지 않는다
#   고친 뒤 여전히 어긋나 있어도 막지 않는다. 그것도 정보다 — 수량을 바로잡았는데
#   아직 맞지 않으면 다른 곳이 틀렸다는 뜻이다. 검산은 조회할 때마다 다시 하므로
#   저장할 것이 없다.
#
# 금액(amount)을 고치는 것을 막지 않는 이유
#   models/amount.py 는 "수량x단가와 어긋나도 **코드가** 이 값을 고치지 않는다" 고
#   적어 뒀다. 사람이 고치는 것은 다르다 — EDITED 의 설계 의도가 "수식을 편집하게
#   하는 대신 값을 고치고 사실을 기록한다" 다. 대신 화면에서 **문서의 오류가
#   감춰진다는 것**을 알린다. 어느 쪽이 맞는지는 사람이 정한다.
# =============================================================================

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.repositories.amount_repository import AmountRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.amount_item import AmountItemRow
from app.services.amount_summary_service import AmountSummaryService
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

# 고칠 수 있는 컬럼. 여기 없는 것은 요청에 들어와도 무시한다.
#
# item_name·source_quote 를 넣지 않은 이유: 그것은 문서에서 읽은 «사실» 이고
# 검산에 쓰이지 않는다. 이름을 고치게 하면 원문과 대조할 수 없게 된다.
_EDITABLE = ("quantity", "unit", "unit_price", "amount", "category")


class AmountItemService:
    def __init__(
        self,
        db: Session,
        amounts: AmountRepository,
        tasks: TaskRepository | None = None,
        task_service: TaskService | None = None,
    ) -> None:
        self._db = db
        self._amounts = amounts
        self._tasks = tasks
        # 고친 결과를 연결된 태스크 설명에 적는 데만 쓴다. 없으면 적지 않는다 —
        # 금액 수정 자체는 태스크와 무관하게 성립한다.
        self._task_service = task_service

    def update(
        self, project_id: int, item_id: int, user_id: int, values: dict
    ) -> AmountItemRow:
        """금액 항목을 고치고 `EDITED` 로 기록한다 (AMT-001-2).

        `values` 에는 **보낸 필드만** 들어 있다(`model_dump(exclude_unset=True)`).
        「안 보냈다」와 「null 로 보냈다」를 구별해야 하므로 스키마가 그 판단을 하고
        여기서는 받은 것만 그대로 넣는다.

        고친 줄 하나를 목록과 **같은 모양**으로 돌려준다. 화면이 전체를 다시 받지
        않고 그 줄만 갈아끼울 수 있고, 무엇보다 **다시 검산한 결과**가 함께 온다 —
        고쳐서 맞게 됐는지 바로 보인다.
        """
        found = self._amounts.get_item(project_id, item_id)
        if found is None:
            raise BusinessError(ErrorCode.AMOUNT_ITEM_NOT_FOUND)
        item, document_id, filename = found

        with transactional(self._db):
            for field in _EDITABLE:
                if field not in values:
                    continue
                setattr(item, field, self._normalize(field, values[field]))
            # 사람이 값을 확인해 고쳤으면 그 자체가 승인이다 (AMT-001-2).
            item.decision = "EDITED"
            item.decided_by = user_id
            item.decided_at = datetime.now(timezone.utc)

        task_ids = (
            self._tasks.suggestion_task_ids(project_id) if self._tasks else {}
        )
        row = AmountSummaryService._to_row(
            item, document_id, filename, task_ids.get(item.id)
        )
        self._note_task(project_id, row, user_id)
        return row

    def _note_task(self, project_id: int, row: AmountItemRow, user_id: int) -> None:
        """이 항목으로 만든 태스크가 있으면 지금 상태를 그 설명에 적는다.

        불일치로 태스크를 만든 뒤(`AMT-004-3`) 금액을 고치면, 보드에 남은 태스크가
        **왜 아직 있는지 알 수 없게 된다.** 삭제하거나 완료로 옮기지 않고 «지금
        상태» 만 적어 둔다 — 판단은 사람이 한다.

        ### 실패해도 금액 수정을 되돌리지 않는다

        이미 커밋된 수정을 «메모를 못 남겼다» 는 이유로 되돌리면 사용자는 고치기가
        실패했다고 읽고 다시 고친다. 실제로는 고쳐져 있다. 이 프로젝트에 같은 판례가
        있다 — `worker.enqueue_build_chunks` 주석의 *"이미 성공해서 커밋된 작업을
        큐 등록 실패 때문에 되돌리면 안 된다"* 다.

        그래서 예외를 삼키고 로그만 남긴다. 놓친 메모는 다음에 그 항목을 고치면
        따라온다.
        """
        if self._task_service is None or row.task_id is None:
            return
        try:
            self._task_service.replace_auto_note(
                project_id, row.task_id, user_id, self._note_text(row)
            )
        except Exception:  # noqa: BLE001 - 이미 성공한 수정을 지키는 것이 우선이다
            logger.exception(
                "태스크 자동 기록에 실패했다. project_id=%s task_id=%s amount_item_id=%s "
                "— 금액 수정은 이미 저장됐다",
                project_id,
                row.task_id,
                row.id,
            )

    @staticmethod
    def _note_text(row: AmountItemRow) -> str:
        """태스크 설명에 넣을 «지금 상태» 한 줄.

        검산 결과가 셋이라 문장도 셋이다. `verified` 의 `False` 와 `None` 을 합치면
        수량·단가가 없는 정상 항목이 «틀렸다» 로 적힌다.
        """
        if row.verified is True:
            return (
                f"검산이 맞았습니다. 수량 × 단가 {row.expected:,}원 "
                f"= 문서 금액 {row.amount:,}원."
            )
        if row.verified is None:
            return "수량이나 단가가 없어 검산할 수 없습니다. 금액은 문서에 적힌 값을 그대로 씁니다."
        gap = row.difference or 0
        return (
            f"아직 어긋납니다. 수량 × 단가 {row.expected:,}원, "
            f"문서 금액 {row.amount:,}원 — 문서 금액이 {abs(gap):,}원 "
            + ("적습니다." if gap > 0 else "많습니다.")
        )

    @staticmethod
    def _normalize(field: str, value):
        """DB 에 넣기 전 다듬는다.

        `category` 는 Enum 으로 들어오는데 컬럼이 `String(20)` 이라 값만 꺼낸다.
        Enum 을 그대로 넣으면 `AmountCategory.DIRECT_LABOR` 문자열이 저장돼
        `ck_amount_category` CHECK 에 걸린다.

        `unit` 의 빈 문자열은 `None` 으로 바꾼다. 사용자가 입력칸을 비운 것은
        「단위가 없다」는 뜻인데, `""` 로 저장하면 «비어 있음» 과 «없음» 이 갈려
        조회마다 두 경우를 다 봐야 한다.
        """
        if value is None:
            return None
        if field == "category":
            return getattr(value, "value", value)
        if field == "unit":
            text = str(value).strip()
            return text or None
        return value
