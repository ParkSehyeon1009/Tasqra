from sqlalchemy.orm import Session, joinedload

from app.models.project import Project, ProjectMember


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, project: Project) -> Project:
        self._db.add(project)
        self._db.flush()
        return project

    def add_member(self, member: ProjectMember) -> ProjectMember:
        self._db.add(member)
        self._db.flush()
        return member

    def get_for_user(self, project_id: int, user_id: int) -> tuple[Project, ProjectMember] | None:
        row = (
            self._db.query(Project, ProjectMember)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(Project.id == project_id, ProjectMember.user_id == user_id)
            .one_or_none()
        )
        return row

    def list_for_user(self, user_id: int) -> list[tuple[Project, ProjectMember]]:
        return (
            self._db.query(Project, ProjectMember)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(ProjectMember.user_id == user_id)
            .order_by(Project.created_at.desc())
            .all()
        )

    def list_members(self, project_id: int) -> list[ProjectMember]:
        return (
            self._db.query(ProjectMember)
            .options(joinedload(ProjectMember.user))
            .filter(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.invited_at)
            .all()
        )

    def get_member(self, project_id: int, user_id: int) -> ProjectMember | None:
        return self._db.query(ProjectMember).filter_by(project_id=project_id, user_id=user_id).one_or_none()

    def delete_member(self, member: ProjectMember) -> None:
        self._db.delete(member)
