# =============================================================================
# 이 파일의 책임: models 패키지의 엔티티 모듈을 미리 import해서 Base.metadata에
#   테이블 정보가 등록되도록 한다. main.py가 Base.metadata.create_all()을
#   호출하기 전에 `import app.models`가 실행되어야 테이블이 실제로 생성된다.
# 다른 파일과의 관계: main.py 참고. document.py/enums.py를 재노출(re-export)해서
#   다른 곳에서는 `from app.models import Document` 처럼 짧게 import할 수 있다.
# Spring 비교: JPA는 @Entity 어노테이션 + 컴포넌트 스캔으로 자동 등록되지만,
#   SQLAlchemy는 클래스가 "import되어 실행"되어야만 매핑이 등록되므로 이렇게
#   패키지 진입점에서 명시적으로 모아 import해준다.
# =============================================================================

from app.models.document import Analysis, Document, ExtractedText
from app.models.enums import AnalyzerType, DocumentStatus, ExtractMethod

__all__ = [
    "Document",
    "ExtractedText",
    "Analysis",
    "DocumentStatus",
    "ExtractMethod",
    "AnalyzerType",
]
from app.models.user import User
from app.models.project import Project, ProjectMember
from app.models.document import Analysis, Document, ExtractedText

__all__ = ["User", "Project", "ProjectMember", "Document", "ExtractedText", "Analysis"]
