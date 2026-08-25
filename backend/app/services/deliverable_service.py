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
from collections.abc import Sequence
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
    FORMAT_FILE_TYPES,
    PERIOD_REQUIRED_KINDS,
    SUPPORTED_DELIVERABLE_FORMATS,
    DeliverableContentResponse,
    DeliverablePreviewResponse,
    PreviewCounts,
)
from app.services.deliverable_html import render_html
from app.services.deliverable_markdown import (
    DeliverableMaterials,
    build_title,
    render_markdown,
)

# 형식별 본문 생성 함수. 형식을 늘릴 때 **여기와 SUPPORTED_DELIVERABLE_FORMATS**
# 두 곳만 고치면 된다. if 문으로 늘리면 형식이 늘 때마다 분기가 깊어진다.
# Spring 비교: Map<String, Renderer> 로 전략을 주입하는 것과 같다.
RENDERERS = {
    "MD": render_markdown,
    "HTML": render_html,
}

logger = logging.getLogger(__name__)

# 보고서 한 절에 넣을 행 수 상한. 수천 행을 넣으면 파일도 크고 사람이 읽지도
# 못한다. 잘렸다는 사실은 source_counts 와 표의 행 수 차이로 드러난다.
MATERIAL_ROW_LIMIT = 200

# 이력 목록에 돌려줄 건수 상한. 페이징을 붙이지 않은 이유는 리포지토리 주석 참고.
HISTORY_LIMIT = 100

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
        # 형식별 본문 생성기는 RENDERERS 에서 고른다. 절을 고르는 규칙은 어느
        # 형식이든 같다(build_document) — 한쪽에만 절을 더하는 실수를 막는다.
        body = RENDERERS[deliverable_format](
            kind=kind,
            title=title,
            period_from=since,
            period_to=until,
            materials=materials,
            generated_at_text=generated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        )

        extension, _ = FORMAT_FILE_TYPES[deliverable_format]
        path = self._write_file(project_id, body, extension)
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

    def preview_content(
        self,
        project_id: int,
        *,
        kind: str,
        deliverable_format: str,
        period_from: date | None = None,
        period_to: date | None = None,
    ) -> DeliverableContentResponse:
        """만들지 않고 **본문만** 만들어 돌려준다 (`DLV-001-2` 를 넓힌 것).

        `generate` 와 **같은 재료·같은 제목·같은 문서 구조**를 쓰고 마지막 두
        단계(파일 쓰기·이력 커밋)만 하지 않는다. 그래서 미리 본 것과 실제로 만든
        것이 어긋날 수 없다 — 두 경로가 갈라지면 "미리보기엔 있었는데 파일엔 없다"
        가 생긴다.

        ### 왜 필요했나

        그전에는 **만들어야** 내용을 볼 수 있었다. 만들면 파일이 생기고 이력에
        남는다. 확인하려고 만든 산출물이 이력에 쌓이는 것을 막을 방법이 없었다.

        `DLV-001-2` 의 「미리보기」는 **건수** 미리보기다(완료 판정이 "건수가 보이고"
        다). 본문 미리보기는 명세에 없던 것이고, 같은 목적(빈 보고서 방지)을 한
        걸음 더 밀어 준다.

        ### 형식 검사도 `generate` 와 똑같다

        없는 형식은 `INVALID_DOCUMENT_TYPE`, 아직 못 만드는 형식은
        `DELIVERABLE_FORMAT_NOT_READY`(501) 다. **미리보기만 되고 만들기는 안 되는
        형식을 만들지 않는다** — 미리 본 뒤 만들기를 눌렀을 때 처음 막히면 헛수고다.

        `XLSX`·`PDF` 가 준비되면 이 메서드는 **그대로** 그 형식을 돌려준다. 형식별
        생성기를 `RENDERERS` 에서 고르는 구조라 여기 고칠 것이 없다.

        ### 화면이 HTML 을 어떻게 안전하게 그리나

        `dangerouslySetInnerHTML` 로 심지 않고 **`<iframe sandbox>` 안에서** 그린다.
        스크립트·폼·부모 접근이 전부 막히므로, 혹시 escape 에 구멍이 생겨도 실행되지
        않는다. `render_html` 이 `<!doctype>` 부터 `<style>` 까지 담은 **완전한 문서**를
        만들기 때문에 그대로 넣으면 된다.

        ### 담을 것이 없으면 `generate` 와 똑같이 막는다

        빈 문서를 미리 보여주는 것은 목적에 어긋난다. 코드도 같은
        `DELIVERABLE_EMPTY` 를 쓴다 — 화면이 두 가지를 따로 처리하지 않게.
        """
        # 형식을 먼저 본다. generate 와 같은 순서·같은 코드다 — 미리보기에서 통과한
        # 형식이 만들기에서 막히면 사용자는 미리 본 것을 만들 수 없다.
        if deliverable_format not in DELIVERABLE_FORMATS:
            raise BusinessError(
                ErrorCode.INVALID_DOCUMENT_TYPE,
                detail=f"출력 형식은 {' · '.join(DELIVERABLE_FORMATS)} 중 하나여야 합니다.",
            )
        if deliverable_format not in SUPPORTED_DELIVERABLE_FORMATS:
            raise BusinessError(
                ErrorCode.DELIVERABLE_FORMAT_NOT_READY,
                detail=(
                    f"{deliverable_format} 형식은 아직 미리 볼 수 없습니다. "
                    f"지금 가능한 형식은 {' · '.join(SUPPORTED_DELIVERABLE_FORMATS)} 입니다."
                ),
            )

        preview = self.preview(
            project_id, kind=kind, period_from=period_from, period_to=period_to
        )
        if not preview.can_generate:
            raise BusinessError(
                ErrorCode.DELIVERABLE_EMPTY, detail=preview.blocked_reason
            )

        since, until = preview.period_from, preview.period_to
        materials = self._materials(project_id, kind=kind, since=since, until=until)
        title = build_title(kind, since, until)
        generated_at = datetime.now(timezone.utc)
        body = RENDERERS[deliverable_format](
            kind=kind,
            title=title,
            period_from=since,
            period_to=until,
            materials=materials,
            generated_at_text=generated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        )
        return DeliverableContentResponse(
            kind=kind,
            title=title,
            format=deliverable_format,
            period_from=since,
            period_to=until,
            body=body,
        )

    def list_history(self, project_id: int) -> list[Deliverable]:
        """만든 산출물 이력 (DLV-003-3).

        파일이 남아 있는지는 여기서 보지 않는다. 목록은 자주 불리는데 건마다
        디스크를 확인하면 파일 수만큼 접근이 생긴다. 없어진 파일은 받으려 할 때
        `DELIVERABLE_FILE_MISSING` 으로 알린다.
        """
        return self._repo.list_by_project(project_id, limit=HISTORY_LIMIT)

    def stale_changes(
        self, project_id: int, rows: Sequence[Deliverable]
    ) -> dict[int, dict[str, int]]:
        """행마다 만든 뒤 늘어난 재료를 센다 (DLV-003-4).

        판정 자체는 모델의 `stale_against` 가 한다 — 그 규칙(늘어난 것만 담는다)이
        이미 거기 있고 테스트도 있다. 여기서 다시 구현하지 않는다.

        ⚠️ **같은 (유형, 기간) 은 한 번만 센다.** 이력이 20건이면 20번 세게 되는데
        재료를 세는 것은 유형과 기간에만 달렸다. 같은 조건으로 여러 번 만든 경우가
        흔하므로(다시 만들기) 캐시가 대부분 맞는다.

        그래도 서로 다른 조건이 많으면 조건 수 × 5 쿼리다. 이력 목록 상한이
        100건이라 최악에는 500쿼리이고, 그만큼 쌓이면 유형별로 한 번에 세는 쿼리로
        바꿔야 한다. 지금 그렇게 하지 않은 이유는 **세는 규칙을 미리보기와 공유해야**
        하고(어긋나면 판정이 틀린다) 아직 이력이 그만큼 쌓이지 않아서다.
        """
        counted: dict[tuple[str, date | None, date | None], dict[str, int]] = {}
        changes: dict[int, dict[str, int]] = {}
        for row in rows:
            key = (row.kind, row.period_from, row.period_to)
            if key not in counted:
                counted[key] = self.snapshot(
                    self._count(
                        project_id,
                        kind=row.kind,
                        since=row.period_from,
                        until=row.period_to,
                    )
                )
            changes[row.id] = row.stale_against(counted[key])
        return changes

    def delete(self, project_id: int, deliverable_id: int) -> None:
        """이력과 파일을 지운다 (DLV-003-3).

        ⚠️ 순서가 중요하다 — **이력을 먼저 지우고 파일을 나중에 지운다.**
        거꾸로 하면 파일을 지운 뒤 커밋이 실패했을 때 "목록에 있는데 받을 수 없는"
        행이 남는다. 이 순서라면 실패해도 남는 것은 아무도 가리키지 않는 파일이고,
        그것은 사용자에게 보이지 않는다.

        파일 삭제가 실패해도 예외를 올리지 않는다. 사용자가 요청한 것은 "이력에서
        지우기" 이고 그것은 이미 됐다.
        """
        row = self._repo.get(project_id, deliverable_id)
        if row is None:
            raise BusinessError(ErrorCode.DELIVERABLE_NOT_FOUND)

        path = row.file_path
        with transactional(self._db) as db:  # type: ignore[arg-type]
            self._repo.remove(row)
            db.flush()
        self._remove_quietly(path)
        logger.info("산출물 삭제 project_id=%s id=%s", project_id, deliverable_id)

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
    def _write_file(project_id: int, body: str, extension: str) -> str:
        """산출물 파일을 저장하고 경로를 돌려준다.

        프로젝트별 폴더에 uuid 이름으로 둔다. 제목을 파일명에 쓰지 않는 이유는
        제목에 한글·공백·특수문자가 들어가고 같은 제목이 여러 번 생기기 때문이다.
        사용자가 받을 때의 이름은 다운로드 응답에서 따로 정한다.
        """
        directory = os.path.join(settings.UPLOAD_DIR, "deliverables", str(project_id))
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{uuid.uuid4().hex}.{extension}")
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
