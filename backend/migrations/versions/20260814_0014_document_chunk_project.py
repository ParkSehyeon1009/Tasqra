"""add project_id to document_chunks for project-scoped vector search

왜 역정규화를 하는가
    프로젝트 범위 벡터 검색(SRH-001 "다른 프로젝트 문서는 제외된다")을 하려면
    거리 정렬에 프로젝트 조건이 함께 걸려야 한다. project_id 가 없으면
    documents 를 조인해서 걸러야 하는데, 그러면 조건이 인덱스 스캔 단계로
    내려가지 않는다.

    pgvector 의 HNSW 는 거리 순으로 후보를 ef_search 개(기본 40)만 꺼내고
    그 다음에 조건을 검사한다. 프로젝트가 전체 청크의 5% 면 40개 중 2개만
    살아남아 결과가 조용히 부족해진다. 에러가 아니라 "결과가 적게 나오는"
    방식으로 실패하므로 발견이 늦다.

    pgvector 0.8.0 이상의 hnsw.iterative_scan 이 이 문제를 풀어주지만,
    그것은 "스캔 중인 테이블에서 평가할 수 있는 조건" 에만 적용된다.
    조인 조건은 해당되지 않는다. 그래서 project_id 를 같은 테이블에 둔다.

    조회 시에는 이렇게 쓴다.
        SET LOCAL hnsw.iterative_scan = strict_order;
        SELECT * FROM document_chunks
        WHERE project_id = :project_id
        ORDER BY embedding <=> :query LIMIT :k;

문서를 다른 프로젝트로 옮기는 기능은 기능명세서에 없다
    그래서 project_id 는 사실상 불변값이고 역정규화 위험이 낮다.
    만약 이동 기능이 생기면 documents.project_id 를 바꿀 때
    document_chunks.project_id 도 같이 갱신해야 한다.

리비전 번호 — 0013 이 아니라 0014 다
    document-async-processing 브랜치가 0013(document_processing_error)을 쓰고 있다.
    origin/main 에는 아직 없어서 main 만 보고는 알 수 없었다. 머지 안 된 원격
    브랜치까지 확인해야 한다.

    down_revision 을 0012 로 두면 0012 에서 두 갈래로 분기해 head 가 둘이 되고
    별도 merge revision 이 필요해진다. 그래서 재정님 0013 뒤에 붙였다.
    => 이 리비전은 document-async-processing 이 main 에 머지된 뒤에 올려야 한다.

컬럼 추가를 3단계로 하는 이유
    NOT NULL 을 한 번에 걸면 기존 행이 있는 개발자의 DB 에서 실패한다.
    nullable 로 넣고 채운 뒤 NOT NULL 로 올린다.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0014"
down_revision = "20260814_0013"
branch_labels = None
depends_on = None


def upgrade():
    # 1) nullable 로 추가한다.
    op.add_column("document_chunks", sa.Column("project_id", sa.BigInteger(), nullable=True))

    # 2) documents 에서 채운다. 청크는 반드시 문서에 속하므로 빈 값이 남지 않는다.
    op.execute(
        """
        UPDATE document_chunks AS c
        SET project_id = d.project_id
        FROM documents AS d
        WHERE d.id = c.document_id
        """
    )

    # 3) NOT NULL 로 올리고 FK 와 인덱스를 붙인다.
    #    FK 이름은 이 레포의 인라인 ForeignKey 가 만들던 PostgreSQL 기본 규칙
    #    ({테이블}_{컬럼}_fkey) 을 그대로 따른다.
    op.alter_column("document_chunks", "project_id", nullable=False)
    op.create_foreign_key(
        "document_chunks_project_id_fkey",
        "document_chunks",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 프로젝트가 아주 작을 때는 HNSW 를 훑는 것보다 이 인덱스로 그 프로젝트의
    # 청크만 읽어 정확한 거리를 계산하는 편이 빠르다. 계획을 고를 여지를 준다.
    op.create_index("ix_chunk_project", "document_chunks", ["project_id", "document_id"])


def downgrade():
    op.drop_index("ix_chunk_project", table_name="document_chunks")
    op.drop_constraint("document_chunks_project_id_fkey", "document_chunks", type_="foreignkey")
    op.drop_column("document_chunks", "project_id")
