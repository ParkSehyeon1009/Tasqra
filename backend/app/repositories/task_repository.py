from sqlalchemy.orm import Session, joinedload

from app.models.project import ProjectMember
from app.models.task import Task


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
