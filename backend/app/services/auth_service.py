from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import BusinessError
from app.core.security import create_access_token, hash_password, verify_password
from app.core.transaction import transactional
from app.models.user import User
from app.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: Session, users: UserRepository) -> None:
        self._db = db
        self._users = users

    def signup(self, login_id: str, email: str, password: str, name: str) -> tuple[User, str]:
        normalized = email.lower().strip()
        normalized_login_id = login_id.lower().strip()
        if self._users.get_by_email(normalized):
            raise BusinessError(ErrorCode.DUPLICATE_USER)
        if self._users.get_by_login_id(normalized_login_id):
            raise BusinessError(ErrorCode.DUPLICATE_LOGIN_ID)
        with transactional(self._db):
            user = self._users.create(User(login_id=normalized_login_id, email=normalized, password_hash=hash_password(password), name=name.strip()))
        return user, create_access_token(user.id)

    def login(self, login_id: str, password: str) -> tuple[User, str]:
        user = self._users.get_by_login_id(login_id)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise BusinessError(ErrorCode.INVALID_CREDENTIALS)
        return user, create_access_token(user.id)
