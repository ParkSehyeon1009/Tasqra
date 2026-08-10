# =============================================================================
# 이 파일의 책임: 여러 Repository 호출을 하나의 트랜잭션으로 묶어 커밋/롤백하는
#   컨텍스트매니저(transactional)를 제공한다. 예를 들어 "문서 저장 + 텍스트
#   저장"처럼 두 단계가 모두 성공해야만 커밋되어야 하는 흐름에 쓴다.
# 다른 파일과의 관계: services/*.py(담당자 A/B/C가 구현)가 Depends(get_db)로
#   받은 Session을 with transactional(db): 블록으로 감싸 사용한다.
#   Service는 DB 세션을 직접 commit/rollback 하지 않고 이 함수를 거친다.
# Spring 비교: Spring의 @Transactional과 동일한 목적. Spring은 어노테이션
#   하나로 AOP가 커밋/롤백을 대신 처리해주지만, FastAPI/SQLAlchemy에는 그런
#   선언적 트랜잭션이 없으므로 with 블록(컨텍스트매니저)으로 명시적으로 감싼다.
#   예외가 나면 rollback 후 그대로 raise하여, 상위의 exceptions.py 핸들러가
#   BusinessError/Exception을 잡아 응답을 만들 수 있게 한다.
# =============================================================================

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def transactional(db: Session) -> Generator[Session, None, None]:
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
