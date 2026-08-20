"""document_chunks.text 에 트라이그램 인덱스 추가 (키워드 검색 SRH-003)

Revision ID: 20260820_0016
Revises: 20260819_0015

왜 필요한가
  의미 검색(SRH-001)은 뜻이 비슷한 것을 찾는다. 그래서 고유명사·숫자·문서번호에
  약하다. "제2026-403호" 를 물으면 벡터는 그 숫자를 특별하게 보지 않는다.

  우리 평가셋 진단에서 **정답 청크의 숫자값이 다른 청크에도 그대로 다 있는 질의가
  26~27%** 였다. 벡터가 가장 약한 자리이고, 키워드 검색이 그 자리를 메운다.

왜 tsvector 가 아니라 트라이그램인가
  PostgreSQL 에는 **한국어 전문검색 설정이 없다.** `simple` 설정은 공백으로만
  토큰을 나누므로 조사가 붙은 한국어에서 어긋난다.

      질의 "계약금액"  본문 "계약금액은"   -> simple tsvector 는 다른 토큰이다

  트라이그램은 글자 3개씩 겹쳐 보므로 조사·붙여쓰기에 걸리지 않는다. 완료 판정이
  "고유명사·숫자·문서번호처럼 **정확한 문자열**로 찾는다" 이므로, 형태소 분석이
  아니라 부분 문자열 매칭이 목적에 맞다.

  gin_trgm_ops 인덱스는 `ILIKE '%...%'` 를 가속한다. 이 인덱스가 없으면
  청크 전체를 순차 훑으므로, 청크가 늘어날수록 그대로 느려진다.

  ⚠ 검색어가 3글자 미만이면 트라이그램이 만들어지지 않아 **인덱스를 쓸 수 없다**
  (순차 스캔으로 떨어진다). 그래서 앱에서 최소 길이를 두고, 2글자는 느릴 수
  있다는 것을 알고 허용한다 — "제1조", "SI" 같은 실제 검색어가 2글자다.

안전한 변경인 이유
  기존 컬럼·제약·인덱스를 하나도 건드리지 않는다. 인덱스 하나와 확장 하나를
  더할 뿐이다. 의미 검색(SRH-001)의 계획에는 영향이 없다 — 그쪽은 ix_chunk_vec
  (HNSW)를 쓰고 이 인덱스는 text 컬럼에만 걸린다.

  다만 **쓰기가 조금 느려진다.** 청크를 넣을 때 GIN 인덱스도 갱신해야 한다.
  청킹은 배치 삽입(bulk_insert)이라 건당 비용이 작고, GIN 은 pending list 로
  삽입을 모아 처리한다(fastupdate 기본 켬).

다른 팀원이 해야 하는 것
  **각자 `alembic upgrade head` 를 돌려야 한다.** 안 돌리면 키워드 검색 API 가
  인덱스 없이 동작하거나(ILIKE 자체는 확장 없이도 된다) 오류가 난다.
  `CREATE EXTENSION` 은 superuser 권한이 필요하다 — docker-compose 의
  postgres 사용자는 superuser 이므로 로컬에서는 문제가 없다.

downgrade 에서 확장을 지우지 않는 이유
  리비전 0011 이 `vector` 확장에 대해 정한 관례를 따른다. 확장은 데이터베이스
  전체의 것이라, 이 리비전만 되돌린다고 지우면 다른 것이 쓰고 있을 때 깨진다.
"""

from alembic import op

revision = "20260820_0016"
down_revision = "20260819_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 트라이그램 연산자·인덱스 지원. 0011 의 vector 와 같은 방식으로 건다.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # models/chunk.py 의 ix_chunk_text_trgm 과 같아야 한다.
    #
    # 부분 인덱스로 좁히지 않는다. project_id 나 embedding_model 로 좁히고 싶지만,
    # 그러면 조건이 인덱스에 박혀 다른 범위의 검색이 이 인덱스를 못 쓴다.
    # 트라이그램 필터로 후보를 줄인 뒤 project_id 조건이 그 위에서 걸린다.
    op.create_index(
        "ix_chunk_text_trgm",
        "document_chunks",
        ["text"],
        postgresql_using="gin",
        postgresql_ops={"text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunk_text_trgm", table_name="document_chunks")
    # pg_trgm 확장은 지우지 않는다 (0011 의 vector 와 같은 이유).
