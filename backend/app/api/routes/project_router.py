from fastapi import APIRouter, Depends, Response
from starlette import status

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.dependencies import ProjectAccess, get_current_user, get_project_access, get_project_owner_access, get_project_repository, get_project_service
from app.models.project import ProjectMember
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import MemberAddRequest, MemberResponse, MemberRoleUpdateRequest, ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.services.project_service import ProjectService

router = APIRouter(prefix="/api/projects", tags=["projects"])

def project_response(project, role: str) -> ProjectResponse:
    return ProjectResponse(
        id=project.id, name=project.name, description=project.description,
        owner_id=project.owner_id, status=project.status,
        started_on=project.started_on, due_on=project.due_on,
        role=role, created_at=project.created_at,
    )

def member_response(member: ProjectMember) -> MemberResponse:
    return MemberResponse(id=member.id, user_id=member.user_id, login_id=member.user.login_id, email=member.user.email, name=member.user.name, role=member.role, invited_at=member.invited_at)

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreateRequest, user: User = Depends(get_current_user), service: ProjectService = Depends(get_project_service)):
    return project_response(service.create(user, **body.model_dump()), "OWNER")

@router.get("", response_model=list[ProjectResponse])
def list_projects(user: User = Depends(get_current_user), service: ProjectService = Depends(get_project_service)):
    return [project_response(project, member.role) for project, member in service.list_for_user(user.id)]

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(access: ProjectAccess = Depends(get_project_access)):
    return project_response(access.project, access.member.role)

@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(body: ProjectUpdateRequest, access: ProjectAccess = Depends(get_project_owner_access), service: ProjectService = Depends(get_project_service)):
    return project_response(service.update(access.project, body.model_dump(exclude_unset=True)), access.member.role)

@router.delete("/{project_id}", status_code=204)
def archive_project(access: ProjectAccess = Depends(get_project_owner_access), service: ProjectService = Depends(get_project_service)):
    service.archive(access.project)
    return Response(status_code=204)

@router.get("/{project_id}/members", response_model=list[MemberResponse])
def list_members(access: ProjectAccess = Depends(get_project_access), repository: ProjectRepository = Depends(get_project_repository)):
    return [member_response(member) for member in repository.list_members(access.project.id)]

@router.post("/{project_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def add_member(body: MemberAddRequest, access: ProjectAccess = Depends(get_project_owner_access), service: ProjectService = Depends(get_project_service), repository: ProjectRepository = Depends(get_project_repository)):
    member = service.add_member(access.project, body.login_id, body.role)
    return member_response(repository.get_member(access.project.id, member.user_id))

def find_member(project_id: int, user_id: int, repository: ProjectRepository) -> ProjectMember:
    member = repository.get_member(project_id, user_id)
    if member is None:
        raise BusinessError(ErrorCode.MEMBER_NOT_FOUND)
    return member

@router.patch("/{project_id}/members/{user_id}", response_model=MemberResponse)
def update_member(user_id: int, body: MemberRoleUpdateRequest, access: ProjectAccess = Depends(get_project_owner_access), service: ProjectService = Depends(get_project_service), repository: ProjectRepository = Depends(get_project_repository)):
    member = find_member(access.project.id, user_id, repository)
    service.update_member(access.project, member, body.role)
    return member_response(member)

@router.delete("/{project_id}/members/{user_id}", status_code=204)
def remove_member(user_id: int, access: ProjectAccess = Depends(get_project_owner_access), service: ProjectService = Depends(get_project_service), repository: ProjectRepository = Depends(get_project_repository)):
    service.remove_member(access.project, find_member(access.project.id, user_id, repository))
    return Response(status_code=204)
