from sqlalchemy.orm import Session, joinedload

from app.models.document import Document, DocumentPage
from app.models.project import Project, ProjectInvitation, ProjectMember


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
            .filter(Project.id == project_id, ProjectMember.user_id == user_id, Project.status == "ACTIVE")
            .one_or_none()
        )
        return row

    def list_for_user(self, user_id: int) -> list[tuple[Project, ProjectMember]]:
        return (
            self._db.query(Project, ProjectMember)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .filter(ProjectMember.user_id == user_id, Project.status == "ACTIVE")
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

    def list_storage_paths(self, project_id: int) -> list[str]:
        originals = self._db.query(Document.storage_path).filter(Document.project_id == project_id).all()
        review_images = self._db.query(DocumentPage.image_path).join(Document).filter(Document.project_id == project_id).all()
        return [path for (path,) in originals + review_images if path]

    def delete_project(self, project: Project) -> None:
        self._db.delete(project)

    def save_invitation(self, invitation: ProjectInvitation) -> ProjectInvitation:
        self._db.add(invitation)
        self._db.flush()
        return invitation

    def get_invitation(self, invitation_id: int) -> ProjectInvitation | None:
        return self._db.query(ProjectInvitation).filter(ProjectInvitation.id == invitation_id).one_or_none()

    def get_invitation_for_user(self, invitation_id: int, user_id: int) -> ProjectInvitation | None:
        return self._db.query(ProjectInvitation).filter(ProjectInvitation.id == invitation_id, ProjectInvitation.invitee_id == user_id).one_or_none()

    def get_project_invitation(self, project_id: int, invitee_id: int) -> ProjectInvitation | None:
        return self._db.query(ProjectInvitation).filter_by(project_id=project_id, invitee_id=invitee_id).one_or_none()

    def list_invitations_for_user(self, user_id: int) -> list[ProjectInvitation]:
        return (
            self._db.query(ProjectInvitation)
            .join(Project, Project.id == ProjectInvitation.project_id)
            .filter(ProjectInvitation.invitee_id == user_id, ProjectInvitation.status == "PENDING", Project.status == "ACTIVE")
            .order_by(ProjectInvitation.created_at.desc())
            .all()
        )

    def list_invitations_for_project(self, project_id: int) -> list[ProjectInvitation]:
        return self._db.query(ProjectInvitation).filter(ProjectInvitation.project_id == project_id).order_by(ProjectInvitation.created_at.desc()).all()

    def list_sent_invitations(self, inviter_id: int) -> list[ProjectInvitation]:
        return (
            self._db.query(ProjectInvitation)
            .options(joinedload(ProjectInvitation.invitee))
            .filter(ProjectInvitation.invited_by == inviter_id)
            .order_by(ProjectInvitation.created_at.desc())
            .all()
        )
