from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.enums import MemberRole
from app.models.enums import ProjectStatus
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository


class ProjectService:
    def __init__(self, db: Session, projects: ProjectRepository, users: UserRepository) -> None:
        self._db, self._projects, self._users = db, projects, users

    def create(self, user: User, **values) -> Project:
        if values.get("started_on") and values.get("due_on") and values["started_on"] > values["due_on"]:
            raise BusinessError(ErrorCode.INVALID_PROJECT_DATES)
        with transactional(self._db):
            project = self._projects.create(Project(owner_id=user.id, **values))
            self._projects.add_member(ProjectMember(project_id=project.id, user_id=user.id, role=MemberRole.OWNER.value))
        return project

    def list_for_user(self, user_id: int):
        return self._projects.list_for_user(user_id)

    def update(self, project: Project, values: dict) -> Project:
        if values.get("name") is None and "name" in values:
            raise BusinessError(ErrorCode.INVALID_PROJECT_NAME)
        for key, value in values.items():
            setattr(project, key, value)
        if project.started_on and project.due_on and project.started_on > project.due_on:
            raise BusinessError(ErrorCode.INVALID_PROJECT_DATES)
        with transactional(self._db):
            self._db.add(project)
        return project

    def archive(self, project: Project) -> None:
        with transactional(self._db):
            project.status = ProjectStatus.ARCHIVED.value

    def add_member(self, project: Project, login_id: str, role: MemberRole) -> ProjectMember:
        user = self._users.get_by_login_id(login_id)
        if user is None:
            raise BusinessError(ErrorCode.USER_NOT_FOUND)
        if self._projects.get_member(project.id, user.id):
            raise BusinessError(ErrorCode.DUPLICATE_MEMBER)
        if role == MemberRole.OWNER:
            raise BusinessError(ErrorCode.OWNER_ROLE_RESERVED)
        with transactional(self._db):
            return self._projects.add_member(ProjectMember(project_id=project.id, user_id=user.id, role=role.value))

    def update_member(self, project: Project, member: ProjectMember, role: MemberRole) -> ProjectMember:
        if member.user_id == project.owner_id or role == MemberRole.OWNER:
            raise BusinessError(ErrorCode.OWNER_ROLE_RESERVED)
        with transactional(self._db):
            member.role = role.value
        return member

    def remove_member(self, project: Project, member: ProjectMember) -> None:
        if member.user_id == project.owner_id:
            raise BusinessError(ErrorCode.OWNER_ROLE_RESERVED)
        with transactional(self._db):
            self._projects.delete_member(member)
