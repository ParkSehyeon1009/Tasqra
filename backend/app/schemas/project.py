from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import MemberRole, ProjectStatus


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    started_on: date | None = None
    due_on: date | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    started_on: date | None = None
    due_on: date | None = None
    status: ProjectStatus | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    owner_id: int
    status: str
    started_on: date | None
    due_on: date | None
    role: str
    created_at: datetime


class MemberAddRequest(BaseModel):
    login_id: str = Field(min_length=3, max_length=50)
    role: MemberRole = MemberRole.VIEWER


class MemberRoleUpdateRequest(BaseModel):
    role: MemberRole


class MemberResponse(BaseModel):
    id: int
    user_id: int
    login_id: str
    email: EmailStr
    name: str
    role: str
    invited_at: datetime


class InvitationResponse(BaseModel):
    id: int
    project_id: int
    project_name: str
    invitee_id: int
    invitee_login_id: str
    invitee_name: str
    inviter_name: str
    role: str
    status: str
    created_at: datetime
