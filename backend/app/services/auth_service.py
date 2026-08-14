from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.security import create_access_token, create_refresh_token, hash_password, hash_refresh_token, verify_password
from app.core.transaction import transactional
from app.models.user import RefreshToken, User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: Session, users: UserRepository) -> None:
        self._db = db
        self._users = users

    def signup(self, login_id: str, email: str, password: str, name: str) -> User:
        normalized = email.lower().strip()
        normalized_login_id = login_id.lower().strip()
        if self._users.get_by_email(normalized):
            raise BusinessError(ErrorCode.DUPLICATE_USER)
        if self._users.get_by_login_id(normalized_login_id):
            raise BusinessError(ErrorCode.DUPLICATE_LOGIN_ID)
        with transactional(self._db):
            return self._users.create(User(login_id=normalized_login_id, email=normalized, password_hash=hash_password(password), name=name.strip()))

    def login(self, login_id: str, password: str) -> tuple[User, str, str]:
        user = self._users.get_by_login_id(login_id)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise BusinessError(ErrorCode.INVALID_CREDENTIALS)
        refresh_token = self._issue_refresh_token(user.id)
        return user, create_access_token(user.id), refresh_token

    def refresh(self, raw_token: str | None) -> tuple[User, str, str]:
        with transactional(self._db):
            stored = self._find_active_refresh_token(raw_token, for_update=True)
            user = stored.user
            stored.revoked_at = datetime.now(timezone.utc)
            raw_new, hash_new = create_refresh_token()
            self._db.add(RefreshToken(user_id=stored.user_id, token_hash=hash_new, expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)))
        return user, create_access_token(user.id), raw_new

    def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        stored = self._db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(raw_token), RefreshToken.revoked_at.is_(None)).one_or_none()
        if stored:
            with transactional(self._db):
                stored.revoked_at = datetime.now(timezone.utc)

    def _issue_refresh_token(self, user_id: int) -> str:
        raw_token, token_hash = create_refresh_token()
        with transactional(self._db):
            self._db.add(RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)))
        return raw_token

    def _find_active_refresh_token(self, raw_token: str | None, *, for_update: bool = False) -> RefreshToken:
        if not raw_token:
            raise BusinessError(ErrorCode.INVALID_REFRESH_TOKEN)
        query = self._db.query(RefreshToken).filter(RefreshToken.token_hash == hash_refresh_token(raw_token), RefreshToken.revoked_at.is_(None))
        if for_update:
            query = query.with_for_update()
        stored = query.one_or_none()
        if stored is None or stored.expires_at <= datetime.now(timezone.utc) or not stored.user.is_active:
            raise BusinessError(ErrorCode.INVALID_REFRESH_TOKEN)
        return stored
