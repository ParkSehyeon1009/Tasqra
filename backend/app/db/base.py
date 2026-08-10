# =============================================================================
# 이 파일의 책임: SQLAlchemy 모델(엔티티)들이 상속할 공통 Base 클래스를 정의한다.
# 다른 파일과의 관계: models/document.py의 Document/ExtractedText/Analysis가
#   이 Base를 상속한다. main.py는 Base.metadata.create_all()로 테이블을 생성한다.
#   (models/__init__.py가 모델 모듈들을 import해야 Base.metadata에 테이블 정보가
#   등록되므로, main.py에서 반드시 app.models를 먼저 import한 뒤 create_all을 호출한다.)
# Spring 비교: JPA의 모든 @Entity가 공유하는 것과 비슷한 위치.
#   차이는 Spring/JPA는 @Entity 어노테이션만 붙이면 컴포넌트 스캔으로 자동
#   등록되지만, SQLAlchemy는 이렇게 공통 Base 클래스를 명시적으로 상속해야 한다.
# =============================================================================

from sqlalchemy.orm import declarative_base

Base = declarative_base()
