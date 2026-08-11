from fastapi import APIRouter, Cookie, Depends, Response
from starlette import status

from app.core.config import settings
from app.dependencies import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])
REFRESH_COOKIE = "tasqra_refresh_token"


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(REFRESH_COOKIE, token, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, httponly=True, secure=settings.refresh_cookie_secure, samesite="lax", path="/api/auth")


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, service: AuthService = Depends(get_auth_service)) -> UserResponse:
    return UserResponse.model_validate(service.signup(body.login_id, body.email, body.password, body.name))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, response: Response, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    user, access_token, refresh_token = service.login(body.login_id, body.password)
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(access_token=access_token, user=UserResponse.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE), service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    user, access_token, rotated_token = service.refresh(refresh_token)
    set_refresh_cookie(response, rotated_token)
    return TokenResponse(access_token=access_token, user=UserResponse.model_validate(user))


@router.post("/logout", status_code=204)
def logout(response: Response, refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE), service: AuthService = Depends(get_auth_service)):
    service.logout(refresh_token)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.status_code = status.HTTP_204_NO_CONTENT


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
