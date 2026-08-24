# =============================================================================
# 이 파일의 책임: 산출물 생성 대상 미리보기(DLV-001-2)를 만든다.
#   리포지토리가 세어 준 건수를 받아 **"만들 수 있는가" 를 판단**하고 응답으로
#   바꾼다. 세는 것은 리포지토리, 판단은 여기다 — dashboard_service 와 같은 구조다.
#
#   완료 판정: "LLM 호출 전에 건수가 보이고 대상이 없으면 생성이 방지된다."
#
# 다른 파일과의 관계
#   repositories/deliverable_repository.py  건수를 세어 준다
#   schemas/deliverable.py                  응답 계약
#   api/routes/deliverable_router.py        이 서비스를 부른다
#   models/deliverable.py                   PERIOD_REQUIRED_KINDS 와 같은 판단
#
# Spring 비교: @Service 다. 읽기만 하므로 @Transactional(readOnly = true) 다.
#
# ⚠ 종류마다 세는 대상이 다르다 — 이것이 이 파일의 핵심이다
#
#   | kind           | 기간   | 무엇을 담나                                |
#   |----------------|--------|--------------------------------------------|
#   | WEEKLY_REPORT  | 필수   | 기간 안의 문서·태스크·결정·일정·금액 변동  |
#   | DECISION_LOG   | 없음   | 결정 **전부**(확정·미결·뒤집힘)            |
#   | MEETING_AGENDA | 없음   | **미결 결정만**(status='PENDING')          |
#   | PROJECT_STATUS | 없음   | 현재 상태 전부                              |
#
#   결정사항 대장에 기간을 걸면 "지난주에 정한 것만" 이 되어 대장이 아니게 된다.
#   회의 안건에 확정된 결정을 넣으면 이미 끝난 것을 또 논의하게 된다.
#   **DB CHECK(ck_deliverable_period_required)가 WEEKLY_REPORT 만 기간을
#   강제하는 것과 같은 판단이다.**
#
# ⚠ 승인 대기는 "담길 내용" 이 아니다
#   기간과 무관하게 세지만 생성 가능 판정에는 넣지 않는다. 승인 대기만 있고
#   확정된 내용이 없으면 보고서는 비어 있다. 화면에는 보여준다 — 사용자가
#   "먼저 승인하고 만들까" 를 판단할 재료다.
# =============================================================================

from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.deliverable import Deliverable
from app.repositories.deliverable_repository import DeliverableRepository
from app.schemas.deliverable import (
    DELIVERABLE_FORMATS,
    DELIVERABLE_KINDS,
    PERIOD_REQUIRED_KINDS,
    SUPPORTED_DELIVERABLE_FORMATS,
    DeliverablePreviewResponse,
    PreviewCounts,
)
from app.services.deliverable_markdown import (
    DeliverableMaterials,
    build_title,
    render_markdown,
)

logger = logging.getLogger(__name__)

# 보고서 한 절에 넣을 행 수 상한. 수천 행을 넣으면 파일도 크고 사람이 읽지도
# 못한다. 잘렸다는 사실은 source_counts 와 표의 행 수 차이로 드러난다.
MATERIAL_ROW_LIMIT = 200

# 갱신 판정(DLV-003-4)에 쓸 스냅샷 키. **미리보기의 건수와 같은 이름**이어야
# 나중에 다시 세어 비교할 수 있다. 승인 대기는 넣지 않는다 — 담기는 재료가
# 아니라 처리해야 할 일이고, 승인 여부로 값이 오가면 "재료가 늘었다" 가 흐려진다.
SNAPSHOT_KEYS = (
    "documents",
    "completed_tasks",
    "decisions",
    "schedule_items",
    "amount_items",
)

# 셀 수 없는 재료. `tasks` 테이블이 리비전 0019 로 생겨 지금은 비어 있다.
# 상수를 지우지 않고 빈 목록으로 두는 이유: 응답의 uncountable 계약을 유지하면
# 다음에 못 세는 재료가 생겨도 화면을 고치지 않고 여기에 이름만 더하면 된다.
UNCOUNTABLE: list[str] = []

__all__ = ["DeliverableService", "UNCOUNTABLE"]


class DeliverableService:
    def __init__(
        self, repository: DeliverableRepository, db: Session | None = None
    ) -> None:
        self._repo = repository
        # 미리보기는 읽기만 해서 세션이 필요 없다. **만들기(generate)는 필요하다** —
        # 파일 저장과 이력 저장을 한 트랜잭션으로 묶어야 하기 때문이다.
        self._db = db

    def preview(
        self,
        project_id: int,
        *,
        kind: str,
        period_from: date | None = None,
        period_to: date | None = None,
    ) -> DeliverablePreviewResponse:
        """산출물에 담길 건수를 세어 돌려준다 (DLV-001-2).

        권한은 라우터의 `get_project_access` 가 이미 판정했다. 여기서 다시 보지
        않는다 — dashboard_service 와 같은 이유로 판단 지점을 늘리지 않는다.
        """
        if kind not in DELIVERABLE_KINDS:
            raise BusinessError(ErrorCode.INVALID_DOCUMENT_TYPE)

        needs_period = kind in PERIOD_REQUIRED_KINDS
        if needs_period and (period_from is None or period_to is None):
            raise BusinessError(ErrorCode.PERIOD_REQUIRED)
        if period_from and period_to and period_from > period_to:
            raise BusinessError(ErrorCode.INVALID_PROJECT_DATES)

        # 기간을 쓰지 않는 유형은 날짜가 와도 무시한다. 그래야 화면이 날짜를
        # 남겨둔 채 유형만 바꿔도 결과가 유형의 뜻대로 나온다.
        since, until = (period_from, period_to) if needs_period else (None, None)
        counts = self._count(project_id, kind=kind, since=since, until=until)

        can_generate = counts.countable_total > 0
        reason = None
        if not can_generate:
            reason = self._blocked_reason(kind, counts)

        logger.info(
            "산출물 미리보기 project_id=%s kind=%s 기간=%s~%s 합=%d 생성가능=%s",
            project_id, kind, since, until, counts.countable_total, can_generate,
        )
        return DeliverablePreviewResponse(
            kind=kind,
            period_from=since,
            period_to=until,
            counts=counts,
            can_generate=can_generate,
            blocked_reason=reason,
            needs_period=needs_period,
            uncountable=list(UNCOUNTABLE),
        )

    def generate(
        self,
        project_id: int,
        *,
        kind: str,
        deliverable_format: str,
        period_from: date | None = None,
        period_to: date | None = None,
        user_id: int | None = None,
    ) -> Deliverable:
        """산출물을 만들어 파일로 저장하고 이력 한 건을 남긴다 (DLV-002-x).

        순서가 중요하다.
          ① 형식을 먼저 본다 — DB 를 건드리기 전에 막을 수 있는 것은 먼저 막는다
          ② 미리보기를 그대로 부른다 — **세는 규칙을 두 번 쓰지 않는다**
          ③ 담을 것이 없으면 만들지 않는다 (DLV-001-2 완료 판정)
          ④ 본문을 만들고 파일에 쓴 뒤 이력을 커밋한다

        ②가 이 함수의 핵심이다. 만들기가 자기만의 집계를 갖게 되면 "미리보기는
        12건이라 했는데 보고서는 9건" 이 생긴다. 그래서 건수는 미리보기 것을 쓰고
        본문에 담는 행만 따로 조회한다(같은 필터를 쓰는 목록 메서드).

        ⚠️ 파일과 이력이 어긋나지 않게 한다
          파일을 먼저 쓰고 이력을 커밋한다. 커밋이 실패하면 **쓴 파일을 지운다.**
          거꾸로 하면(이력 먼저) 목록에 있는데 받을 수 없는 행이 남는다.
        """
        if deliverable_format not in DELIVERABLE_FORMATS:
            raise BusinessError(
                ErrorCode.INVALID_DOCUMENT_TYPE,
                detail=f"출력 형식은 {' · '.join(DELIVERABLE_FORMATS)} 중 하나여야 합니다.",
            )
        if deliverable_format not in SUPPORTED_DELIVERABLE_FORMATS:
            raise BusinessError(
                ErrorCode.DELIVERABLE_FORMAT_NOT_READY,
                detail=(
                    f"{deliverable_format} 형식은 아직 만들 수 없습니다. "
                    f"지금 가능한 형식은 {' · '.join(SUPPORTED_DELIVERABLE_FORMATS)} 입니다."
                ),
            )

        preview = self.preview(
            project_id, kind=kind, period_from=period_from, period_to=period_to
        )
        if not preview.can_generate:
            # 왜 못 만드는지는 미리보기가 이미 문장으로 만들어 뒀다. 여기서 다시
            # 쓰면 두 곳의 문구가 갈린다.
            #
            # 코드를 새로 만들지 않고 **이미 있던 DELIVERABLE_EMPTY 를 쓴다.**
            # 뜻이 같은 코드를 하나 더 만들면 화면이 둘 다 처리해야 한다.
            raise BusinessError(
                ErrorCode.DELIVERABLE_EMPTY, detail=preview.blocked_reason
            )

        since, until = preview.period_from, preview.period_to
        materials = self._materials(project_id, kind=kind, since=since, until=until)
        title = build_title(kind, since, until)
        generated_at = datetime.now(timezone.utc)
        body = render_markdown(
            kind=kind,
            title=title,
            period_from=since,
            period_to=until,
            materials=materials,
            generated_at_text=generated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        )

        path = self._write_file(project_id, body)
        try:
            with transactional(self._db) as db:  # type: ignore[arg-type]
                row = self._repo.add(
                    Deliverable(
                        project_id=project_id,
                        kind=kind,
                        format=deliverable_format,
                        period_from=since,
                        period_to=until,
                        title=title,
                        file_path=path,
                        file_size=os.path.getsize(path),
                        source_counts_json=self.snapshot(preview.counts),
                        generated_by=user_id,
                        generated_at=generated_at,
                    )
                )
                db.flush()
        except Exception:
            self._remove_quietly(path)
            raise

        logger.info(
            "산출물 생성 project_id=%s kind=%s format=%s 기간=%s~%s 크기=%s",
            project_id, kind, deliverable_format, since, until, row.file_size,
        )
        return row

    def open_file(self, project_id: int, deliverable_id: int) -> Deliverable:
        """다운로드할 산출물을 찾는다 (DLV-003-3).

        파일이 사라진 경우를 404 와 구분한다. 목록에는 보이는데 받을 수 없는
        상황이라, 같은 오류로 뭉치면 "왜 목록에 있나" 를 설명할 수 없다.
        """
        row = self._repo.get(project_id, deliverable_id)
        if row is None:
            raise BusinessError(ErrorCode.DELIVERABLE_NOT_FOUND)
        if not os.path.exists(row.file_path):
            logger.warning(
                "산출물 파일 없음 id=%s path=%s", deliverable_id, row.file_path
            )
            raise BusinessError(ErrorCode.DELIVERABLE_FILE_MISSING)
        return row

    @staticmethod
    def snapshot(counts: PreviewCounts) -> dict[str, int]:
        """만든 시점의 재료 개수. 갱신 판정(DLV-003-4)의 근거가 된다."""
        return {key: getattr(counts, key) for key in SNAPSHOT_KEYS}

    # --- 내부 ---------------------------------------------------------------

    def _materials(
        self, project_id: int, *, kind: str, since: date | None, until: date | None
    ) -> DeliverableMaterials:
        """본문에 담을 행. **_count 의 표와 같은 규칙**이어야 한다."""
        if kind == "MEETING_AGENDA":
            return DeliverableMaterials(
                decisions=self._repo.list_decisions(
                    project_id, status="PENDING", limit=MATERIAL_ROW_LIMIT
                )
            )
        if kind == "DECISION_LOG":
            return DeliverableMaterials(
                decisions=self._repo.list_decisions(project_id, limit=MATERIAL_ROW_LIMIT)
            )
        return DeliverableMaterials(
            documents=self._repo.list_documents(
                project_id, since=since, until=until, limit=MATERIAL_ROW_LIMIT
            ),
            completed_tasks=self._repo.list_completed_tasks(
                project_id, since=since, until=until, limit=MATERIAL_ROW_LIMIT
            ),
            decisions=self._repo.list_decisions(
                project_id, since=since, until=until, limit=MATERIAL_ROW_LIMIT
            ),
            schedule_items=self._repo.list_schedule_items(
                project_id, since=since, until=until, limit=MATERIAL_ROW_LIMIT
            ),
            amount_items=self._repo.list_amount_items(
                project_id, since=since, until=until, limit=MATERIAL_ROW_LIMIT
            ),
        )

    @staticmethod
    def _write_file(project_id: int, body: str) -> str:
        """산출물 파일을 저장하고 경로를 돌려준다.

        프로젝트별 폴더에 uuid 이름으로 둔다. 제목을 파일명에 쓰지 않는 이유는
        제목에 한글·공백·특수문자가 들어가고 같은 제목이 여러 번 생기기 때문이다.
        사용자가 받을 때의 이름은 다운로드 응답에서 따로 정한다.
        """
        directory = os.path.join(settings.UPLOAD_DIR, "deliverables", str(project_id))
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{uuid.uuid4().hex}.md")
        with open(path, "w", encoding="utf-8") as file:
            file.write(body)
        return path

    @staticmethod
    def _remove_quietly(path: str) -> None:
        """정리에 실패해도 원래 예외를 가리지 않는다."""
        try:
            os.remove(path)
        except OSError:
            logger.warning("산출물 임시 파일 정리 실패 path=%s", path, exc_info=True)

    def _count(
        self, project_id: int, *, kind: str, since: date | None, until: date | None
    ) -> PreviewCounts:
        """종류에 맞는 재료만 센다. 머리말의 표가 이 함수의 규칙이다."""
        pending = self._repo.count_pending_suggestions(project_id)

        if kind == "MEETING_AGENDA":
            # 미결 결정만 안건이 된다. 리비전 0007 주석:
            # "status='PENDING' 인 항목이 그대로 다음 회의 안건이 된다."
            # 문서·일정·금액은 안건의 재료가 아니다.
            return PreviewCounts(
                documents=0,
                decisions=self._repo.count_decisions(project_id, status="PENDING"),
                schedule_items=0,
                amount_items=0,
                completed_tasks=0,
                pending_suggestions=pending,
            )

        if kind == "DECISION_LOG":
            # 결정 전부. 기간을 걸지 않는다 — 걸면 대장이 아니게 된다.
            return PreviewCounts(
                documents=0,
                decisions=self._repo.count_decisions(project_id),
                schedule_items=0,
                amount_items=0,
                completed_tasks=0,
                pending_suggestions=pending,
            )

        # WEEKLY_REPORT · PROJECT_STATUS — 다섯 종류를 모두 담는다.
        # 주간 보고서는 기간이 있고 현황 한 장은 없다(since·until 이 None).
        return PreviewCounts(
            documents=self._repo.count_documents(project_id, since=since, until=until),
            decisions=self._repo.count_decisions(project_id, since=since, until=until),
            schedule_items=self._repo.count_schedule_items(
                project_id, since=since, until=until
            ),
            amount_items=self._repo.count_amount_items(
                project_id, since=since, until=until
            ),
            completed_tasks=self._repo.count_completed_tasks(
                project_id, since=since, until=until
            ),
            pending_suggestions=pending,
        )

    @staticmethod
    def _blocked_reason(kind: str, counts: PreviewCounts) -> str:
        """왜 만들 수 없는지 사람이 읽는 문장으로.

        화면이 그대로 보여줄 수 있어야 한다. 코드를 보고 문장을 만들게 하면
        같은 판단이 두 곳에 생긴다.

        승인 대기가 남아 있으면 그것을 알린다 — 승인하면 담길 내용이 생긴다는
        뜻이므로 사용자가 다음에 할 일을 안다.
        """
        if counts.pending_suggestions > 0:
            return (
                f"담을 내용이 없습니다. 승인 대기 중인 제안이 "
                f"{counts.pending_suggestions}건 있습니다 — 승인하면 담깁니다."
            )
        if kind == "MEETING_AGENDA":
            return "미결 상태인 결정사항이 없습니다. 안건으로 낼 것이 없습니다."
        if kind == "DECISION_LOG":
            return "기록된 결정사항이 없습니다."
        if kind == "WEEKLY_REPORT":
            return "선택한 기간에 문서·태스크·결정·일정·금액 변동이 없습니다."
        return "프로젝트에 담을 내용이 아직 없습니다."
