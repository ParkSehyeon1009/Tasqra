# =============================================================================
# 이 파일의 책임: 여러 계층이 함께 봐야 하는 상수를 의존성 없이 담는다.
#   이 모듈은 아무것도 import 하지 않는다. 그래서 SQLAlchemy · pydantic 이 없는
#   환경에서도 읽을 수 있고, 순환 import 도 생기지 않는다.
# 다른 파일과의 관계: models/chunk.py 가 EMBEDDING_DIM 을 여기서 가져와
#   컬럼 정의와 CHECK 제약에 쓰고, embedding/fake_client.py 와
#   services/chunking_service.py 도 같은 값을 본다.
#   EMBEDDING_DIM 이 models/chunk.py 안에 있었을 때는 가짜 임베더가 상수 하나
#   때문에 ORM 전체를 끌어와, DB 드라이버 없이 단독 검증을 할 수 없었다.
# Spring 비교: public static final 상수를 모아 둔 Constants 클래스이거나,
#   엔티티와 서비스가 함께 참조하는 공용 상수 모듈에 해당한다.
# =============================================================================

# 채택 임베딩 모델의 출력 차원.
#
# dragonkue/BGE-m3-ko · KURE-v1 · snowflake-arctic-embed-l-v2.0 이 모두 1024라서
# 모델을 바꿔도 DB 스키마는 그대로다. 세현님이 BGE-m3-ko 를 파인튜닝해도
# 아키텍처가 같으므로 이 값은 변하지 않는다.
#
# document_chunks 에 embedding_dim = 1024 CHECK 제약이 걸려 있으므로, 이 값을
# 바꾸면 마이그레이션이 함께 필요하다. 값만 고치면 INSERT 가 전부 실패한다.
EMBEDDING_DIM = 1024
