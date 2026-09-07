from sqlalchemy.orm import Session, joinedload

from app.models.project import ProjectMember
from app.models.task import Task, TaskActivityLog


class TaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, task: Task) -> Task:
        self._db.add(task)
        self._db.flush()
        return task

    def list_by_project(self, project_id: int) -> list[Task]:
        return (
            self._db.query(Task)
            .options(joinedload(Task.assignee))
            .filter(Task.project_id == project_id)
            .order_by(Task.created_at.desc(), Task.id.desc())
            .all()
        )

    def suggestion_task_ids(self, project_id: int) -> dict[int, int]:
        """{제안 id: 태스크 id}. 제안으로 만든 태스크가 이미 있는지 보는 용도다.

        `origin = 'AI_APPROVED'` 인 태스크만 본다. 사람이 직접 만든 태스크는
        `source_suggestion_id` 가 없다.

        이 메서드는 금액 불일치에서 만든 태스크를 찾으므로 분리된
        `source_amount_item_id` 를 조회한다. 문서 액션 태스크 제안은
        `source_suggestion_id` 로 별도 추적한다.

        한 번에 다 가져오는 이유: 목록 화면이 항목마다 따로 물으면 N+1 이 된다.
        한 프로젝트의 AI 태스크는 많아도 수백 건이라 전부 담아도 무겁지 않다.
        """
        rows = (
            self._db.query(Task.source_amount_item_id, Task.id)
            .filter(
                Task.project_id == project_id,
                Task.origin == "AI_APPROVED",
                Task.source_amount_item_id.isnot(None),
            )
            .all()
        )
        return {int(row[0]): int(row[1]) for row in rows}

    def get(self, project_id: int, task_id: int) -> Task | None:
        return (
            self._db.query(Task)
            .options(joinedload(Task.assignee))
            .filter(Task.project_id == project_id, Task.id == task_id)
            .one_or_none()
        )

    def is_project_member(self, project_id: int, user_id: int) -> bool:
        return self._db.query(ProjectMember.id).filter_by(project_id=project_id, user_id=user_id).first() is not None

    def delete(self, task: Task) -> None:
        self._db.delete(task)

    def add_activity(self, activity: TaskActivityLog) -> TaskActivityLog:
        self._db.add(activity)
        self._db.flush()
        return activity

    def list_activity(self, project_id: int, limit: int = 100) -> list[TaskActivityLog]:
        return (
            self._db.query(TaskActivityLog)
            .options(joinedload(TaskActivityLog.actor))
            .filter(TaskActivityLog.project_id == project_id)
            .order_by(TaskActivityLog.created_at.desc(), TaskActivityLog.id.desc())
            .limit(limit)
            .all()
        )
