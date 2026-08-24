from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.task import Task, TaskActivityLog
from app.repositories.task_repository import TaskRepository


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
