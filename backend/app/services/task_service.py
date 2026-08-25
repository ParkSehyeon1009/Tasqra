from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.task import Task, TaskActivityLog
from app.repositories.task_repository import TaskRepository

# 설명 끝의 «자동 기록» 블록을 여는 표시. 시스템이 붙인 문장과 사람이 쓴 설명을
# 가르는 유일한 기준이다.
#
# ⚠ **화면과 글자까지 같아야 한다** — frontend/src/utils/taskNote.js 의
#   AUTO_NOTE_MARKER 다. 한 글자라도 다르면 보드 카드가 블록을 못 찾아서 색이 안
#   입고 본문에 섞여 나온다. 에러가 나지 않으므로 알아채기 어렵다.
AUTO_NOTE_MARKER = "── 자동 기록 ──"


class TaskService:
    def __init__(self, db: Session, tasks: TaskRepository) -> None:
        self._db = db
        self._tasks = tasks

    def list(self, project_id: int) -> list[Task]:
        return self._tasks.list_by_project(project_id)

    def list_activity(self, project_id: int) -> list[TaskActivityLog]:
        return self._tasks.list_activity(project_id)

    def get(self, project_id: int, task_id: int) -> Task:
        task = self._tasks.get(project_id, task_id)
        if task is None:
            raise BusinessError(ErrorCode.TASK_NOT_FOUND)
        return task

    def create(self, project_id: int, user_id: int, values: dict, *, origin: str = "MANUAL", source_suggestion_id: int | None = None) -> Task:
        values["title"] = values["title"].strip()
        if not values["title"]:
            raise BusinessError(ErrorCode.INVALID_TASK_TITLE)
        self._validate_due_on(values.get("due_on"))
        self._validate_assignee(project_id, values.get("assignee_id"))
        with transactional(self._db):
            task = self._tasks.create(Task(project_id=project_id, created_by=user_id, origin=origin, source_suggestion_id=source_suggestion_id, **values))
            self._record(task, user_id, "CREATED", {"origin": origin, "source_suggestion_id": source_suggestion_id})
        return self.get(project_id, task.id)

    def update(self, project_id: int, task_id: int, user_id: int, values: dict) -> Task:
        task = self.get(project_id, task_id)
        if "title" in values:
            if values["title"] is None or not values["title"].strip():
                raise BusinessError(ErrorCode.INVALID_TASK_TITLE)
            values["title"] = values["title"].strip()
        if "assignee_id" in values:
            self._validate_assignee(project_id, values["assignee_id"])
        if "due_on" in values:
            self._validate_due_on(values["due_on"])

        requested_keys = set(values)
        changes = {
            key: {"before": self._json_value(getattr(task, key)), "after": self._json_value(value)}
            for key, value in values.items()
            if self._json_value(getattr(task, key)) != self._json_value(value)
        }

        next_status = values.get("status", task.status)
        if next_status == "DONE" and task.status != "DONE":
            values["completed_at"] = datetime.now(timezone.utc)
        elif next_status != "DONE" and task.status == "DONE":
            values["completed_at"] = None

        with transactional(self._db):
            for key, value in values.items():
                setattr(task, key, value)
            self._db.add(task)
            if changes:
                event_type = "STATUS_CHANGED" if "status" in requested_keys else "UPDATED"
                self._record(task, user_id, event_type, {"changes": changes})
        return self.get(project_id, task.id)

    def delete(self, project_id: int, task_id: int, user_id: int) -> None:
        task = self.get(project_id, task_id)
        with transactional(self._db):
            self._record(task, user_id, "DELETED", {"origin": task.origin})
            self._tasks.delete(task)

    def replace_auto_note(
        self, project_id: int, task_id: int, actor_id: int, note: str
    ) -> Task:
        """설명 끝의 **자동 기록 블록**을 갈아끼운다.

        금액 항목을 고쳐서 검산 결과가 바뀌었을 때처럼, 시스템이 태스크에 «지금
        상태» 를 알려야 하는 자리에서 쓴다.

        ### 사람이 쓴 부분을 건드리지 않는다

        구분자(`AUTO_NOTE_MARKER`) 앞은 그대로 두고 뒤만 바꾼다. 그래서 사용자가
        태스크에 적어 둔 메모가 사라지지 않는다.

        ### 쌓이지 않는다

        **블록 하나를 통째로 교체**한다. 여러 번 고쳐도 마지막 상태만 남는다.
        이력이 필요하면 활동 기록(`task_activity_logs`)에 남는다 — 그쪽이 이력을
        담는 자리다.

        ### 시각을 적지 않는다

        이 블록은 **현재 상태**이고 이력이 아니다. 시각을 적으면 로그처럼 보여서
        "왜 한 줄만 있나" 가 된다. 언제 바뀌었는지는 활동 기록에 있다.

        ### 상태(status)를 바꾸지 않는다

        검산이 맞았다고 시스템이 `DONE` 으로 옮기지 않는다. `completed_at` 이
        주간 보고서의 재료(`DLV-002-1`)라서, 시스템이 임의로 찍으면 **보고서에
        "이 주에 이 일을 끝냈다" 는 거짓이 들어간다.** 일이 끝났는지는 사람이 정한다.

        Spring 비교: 도메인 이벤트를 받아 엔티티의 표시용 필드만 갱신하는
        핸들러 자리다.
        """
        task = self.get(project_id, task_id)
        written = (task.description or "").split(AUTO_NOTE_MARKER)[0].rstrip()
        with transactional(self._db):
            task.description = f"{written}\n\n{AUTO_NOTE_MARKER}\n{note}".lstrip()
            self._record(task, actor_id, "AUTO_NOTE", {"note": note})
        return self.get(project_id, task_id)

    def _record(self, task: Task, actor_id: int, event_type: str, details: dict) -> None:
        self._tasks.add_activity(TaskActivityLog(project_id=task.project_id, task_id=task.id, task_title=task.title, event_type=event_type, actor_id=actor_id, details=details))

    @staticmethod
    def _json_value(value):
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    def _validate_assignee(self, project_id: int, assignee_id: int | None) -> None:
        if assignee_id is not None and not self._tasks.is_project_member(project_id, assignee_id):
            raise BusinessError(ErrorCode.TASK_ASSIGNEE_NOT_MEMBER)

    @staticmethod
    def _validate_due_on(due_on: date | None) -> None:
        if due_on is not None and due_on < date.today():
            raise BusinessError(ErrorCode.INVALID_TASK_DUE_DATE)
