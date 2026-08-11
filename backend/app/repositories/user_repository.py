from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, user: User) -> User:
        self._db.add(user)
        self._db.flush()
        return user

    def get_by_id(self, user_id: int) -> User | None:
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._db.query(User).filter(User.email == email.lower().strip()).one_or_none()

    def get_by_login_id(self, login_id: str) -> User | None:
        normalized = login_id.lower().strip()
        return self._db.query(User).filter(User.login_id == normalized).one_or_none()
