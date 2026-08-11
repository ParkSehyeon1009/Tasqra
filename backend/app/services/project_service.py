import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.transaction import transactional
from app.models.enums import MemberRole
from app.models.project import Project, ProjectInvitation, ProjectMember
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

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

    def delete(self, project: Project) -> None:
        storage_paths = self._projects.list_storage_paths(project.id)
        with transactional(self._db):
            self._projects.delete_project(project)
        for storage_path in storage_paths:
            try:
                if os.path.exists(storage_path):
                    os.remove(storage_path)
            except OSError:
                logger.warning("프로젝트 삭제 후 원본 파일 정리 실패: %s", storage_path)

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

    def invite_member(self, project: Project, inviter: User, login_id: str, role: MemberRole) -> ProjectInvitation:
        user = self._users.get_by_login_id(login_id)
        if user is None:
            raise BusinessError(ErrorCode.USER_NOT_FOUND)
        if user.id == inviter.id or self._projects.get_member(project.id, user.id):
            raise BusinessError(ErrorCode.DUPLICATE_MEMBER)
        if role == MemberRole.OWNER:
            raise BusinessError(ErrorCode.OWNER_ROLE_RESERVED)
        invitation = self._projects.get_project_invitation(project.id, user.id)
        with transactional(self._db):
            if invitation is None:
                invitation = ProjectInvitation(project_id=project.id, invitee_id=user.id, invited_by=inviter.id, role=role.value, status="PENDING")
            else:
                invitation.role = role.value
                invitation.status = "PENDING"
                invitation.invited_by = inviter.id
                invitation.created_at = datetime.now(timezone.utc)
                invitation.responded_at = None
            return self._projects.save_invitation(invitation)

    def accept_invitation(self, invitation: ProjectInvitation) -> None:
        if invitation.status != "PENDING":
            raise BusinessError(ErrorCode.INVITATION_NOT_PENDING)
        with transactional(self._db):
            if not self._projects.get_member(invitation.project_id, invitation.invitee_id):
                self._projects.add_member(ProjectMember(project_id=invitation.project_id, user_id=invitation.invitee_id, role=invitation.role))
            invitation.status = "ACCEPTED"
            invitation.responded_at = datetime.now(timezone.utc)

    def decline_invitation(self, invitation: ProjectInvitation) -> None:
        if invitation.status != "PENDING":
            raise BusinessError(ErrorCode.INVITATION_NOT_PENDING)
        with transactional(self._db):
            invitation.status = "DECLINED"
            invitation.responded_at = datetime.now(timezone.utc)

    def cancel_invitation(self, invitation: ProjectInvitation) -> None:
        if invitation.status != "PENDING":
            raise BusinessError(ErrorCode.INVITATION_NOT_PENDING)
        with transactional(self._db):
            invitation.status = "CANCELED"
            invitation.responded_at = datetime.now(timezone.utc)

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
