# =============================================================================
# 이 파일의 책임: DB 연결(engine)과 세션 팩토리(SessionLocal)를 만들고,
#   요청마다 세션을 하나씩 열고 닫아주는 FastAPI 의존성(get_db)을 제공한다.
# 다른 파일과의 관계: core/config.py의 settings.DATABASE_URL로 engine을 만든다.
#   repositories/*.py는 이 세션을 주입받아 쿼리를 실행하고, main.py는 이 engine으로
#   Base.metadata.create_all()을 호출한다.
# Spring 비교: DataSource + JdbcTemplate(또는 EntityManager)을 합쳐놓은 위치.
#   get_db()는 Spring이 요청 스코프 EntityManager를 열고 트랜잭션 끝나면 자동으로
#   닫아주는 것과 같은 역할을 하는데, FastAPI는 이걸 명시적으로 Depends()에 넣어
#   제너레이터로 직접 작성해야 한다 (try/finally로 close 보장).
#   이 프로젝트는 6일 일정이므로 async DB(SQLAlchemy async engine)는 도입하지
#   않고 동기 세션만 사용한다 — 동기 라우터(def)에서 threadpool로 실행된다.
# =============================================================================

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
