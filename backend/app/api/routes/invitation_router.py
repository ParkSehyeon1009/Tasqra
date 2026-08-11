from fastapi import APIRouter, Depends, Response

from app.api.routes.project_router import invitation_response
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.dependencies import get_current_user, get_project_repository, get_project_service
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import InvitationResponse
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


@router.get("", response_model=list[InvitationResponse])
def list_my_invitations(user: User = Depends(get_current_user), repository: ProjectRepository = Depends(get_project_repository)):
    return [invitation_response(item) for item in repository.list_invitations_for_user(user.id)]


@router.get("/recent-invitees")
def list_recent_invitees(user: User = Depends(get_current_user), repository: ProjectRepository = Depends(get_project_repository)):
    result, seen = [], set()
    for item in repository.list_sent_invitations(user.id):
        if item.invitee_id in seen:
            continue
        seen.add(item.invitee_id)
        result.append({"login_id": item.invitee.login_id, "name": item.invitee.name})
    return result[:10]


def invitation_for_user(invitation_id: int, user: User, repository: ProjectRepository):
    invitation = repository.get_invitation_for_user(invitation_id, user.id)
    if invitation is None:
        raise BusinessError(ErrorCode.INVITATION_NOT_FOUND)
    return invitation


@router.post("/{invitation_id}/accept", status_code=204)
def accept_invitation(invitation_id: int, user: User = Depends(get_current_user), repository: ProjectRepository = Depends(get_project_repository), service: ProjectService = Depends(get_project_service)):
    service.accept_invitation(invitation_for_user(invitation_id, user, repository))
    return Response(status_code=204)


@router.post("/{invitation_id}/decline", status_code=204)
def decline_invitation(invitation_id: int, user: User = Depends(get_current_user), repository: ProjectRepository = Depends(get_project_repository), service: ProjectService = Depends(get_project_service)):
    service.decline_invitation(invitation_for_user(invitation_id, user, repository))
    return Response(status_code=204)
