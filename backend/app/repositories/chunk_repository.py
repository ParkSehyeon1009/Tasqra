# =============================================================================
# 이 파일의 책임: document_chunks 테이블에 대한 조회 · 삽입 · 삭제를 담당한다.
#   비즈니스 판단은 하지 않는다 (그건 services/chunking_service.py 가 한다).
# 다른 파일과의 관계: models/chunk.py 의 DocumentChunk 를 다룬다.
#   services/chunking_service.py 가 이것을 주입받아 쓴다.
#   dependencies.py 의 get_chunk_repository() 가 세션을 감싸 만든다.
# Spring 비교: JpaRepository 를 상속한 인터페이스 + 커스텀 쿼리 메서드에 대응한다.
#   Session 을 생성자로 받는 것은 EntityManager 주입과 같다. commit 은 여기서
#   하지 않는다 — 서비스가 트랜잭션 경계를 잡는다(@Transactional 이 서비스에
#   붙는 것과 같은 이유).
# =============================================================================

from __future__ import annotations

import re
from typing import Sequence

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.models.chunk import DocumentChunk

# 실행계획 안의 벡터 리터럴. EXPLAIN 은 바인드 파라미터를 못 받아서 1024개 숫자가
# 문장에 그대로 박히고, 계획 출력에도 그대로 찍혀 화면을 덮는다.
_VECTOR_LITERAL = re.compile(r"'\[[-0-9eE.,\s]{60,}\]'::vector")

# 실행계획에서 판단에 필요한 줄. 이것만 남기면 사람이 읽을 수 있다.
#
# ⚠ 읽는 법을 착각하기 쉽다. project_id 가 "Index Cond" 로 나오기를 기대하면 안 된다.
#   HNSW 인덱스에는 벡터 컬럼만 들어 있으므로 project_id 는 구조적으로 Index Cond
#   가 될 수 없다. 근사 인덱스는 ef_search 개의 후보를 먼저 만들고 그 다음에
#   WHERE 를 적용한다 (pgvector 문서: "filtering is applied after the index is
#   scanned"). 그래서 project_id 는 항상 "Filter" 로 나온다. 그것이 정상이다.
#
#   중요한 것은 그 Filter 가 **어느 노드에 붙는가** 다.
#     · Index Scan using ix_chunk_vec 노드의 Filter  -> iterative_scan 이 부족분을
#       감지해 인덱스를 더 훑는다. 우리가 원하는 상태다.
#     · 그 위 노드(Nested Loop · Hash Join)의 Join Filter -> HNSW 스캔은 자기가
#       걸러졌다는 것을 모르므로 더 꺼내오지 않는다. 결과가 조용히 적어진다.
#       리비전 0014 가 피하려던 것이 정확히 이것이다.
#
#   Index Scan / Seq Scan  — 무엇으로 훑었나 (ix_chunk_vec 이면 벡터 인덱스)
#   Order By               — 벡터 인덱스로 정렬했나
#   Filter / Rows Removed  — 어느 노드에서 걸렀나, 얼마나 버렸나
#   Sort Method            — 인덱스를 못 쓰고 메모리 정렬로 떨어졌나
#   Join Filter            — 조인 밖에서 걸렀나 (0014 가 피하려던 것)
_PLAN_KEEP = (
    "Index Scan",
    "Seq Scan",
    "Bitmap",
    "Index Cond",
    "Filter:",
    "Rows Removed",
    "Order By:",
    "Sort Method",
    "Sort Key",
    "Limit",
    "Join",
    "Nested Loop",
    "Hash",
    "Planning Time",
    "Execution Time",
)


def mask_vector_literals(plan: str) -> str:
    """실행계획에서 벡터 리터럴을 짧게 바꾼다."""
    return _VECTOR_LITERAL.sub("'[...1024차원 생략...]'::vector", plan)


def summarize_plan(plan: str) -> str:
    """실행계획에서 판단에 필요한 줄만 남긴다.

    Output: 줄(VERBOSE 가 만드는 컬럼 목록)과 Buffers 줄을 빼면 화면에 들어온다.
    전문이 필요하면 explain_search(summary_only=False) 를 쓴다.
    """
    kept: list[str] = []
    for line in plan.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Output:") or stripped.startswith("Buffers:"):
            continue
        if any(token in stripped for token in _PLAN_KEEP):
            kept.append(line)
    return "\n".join(kept) if kept else plan


class ChunkRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # --- 조회 ---------------------------------------------------------------

    def count_for_document(self, document_id: int) -> int:
        stmt = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
        return int(self._db.execute(stmt).scalar_one())

    def list_for_document(self, document_id: int) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.seq)
        )
        return list(self._db.execute(stmt).scalars())

    def stale_document_ids(self, project_id: int) -> list[int]:
        """본문이 수정됐는데 재청킹이 안 된 문서를 찾는다.

        청크의 text_version 이 extracted_texts.text_version 보다 작으면 낡은
        것이다 (models/chunk.py 의 ix_chunk_stale 인덱스가 이 조회용이다).
        RAG-09(검수 확정 시 재임베딩)가 놓친 문서를 찾는 데 쓴다.
        """
        # ExtractedText 를 여기서 import 하면 순환이 생기지 않는다 (모델끼리는
        # 이미 서로를 알고 있다).
        from app.models.document import Document, ExtractedText

        stmt = (
            select(DocumentChunk.document_id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(ExtractedText, ExtractedText.document_id == Document.id)
            .where(DocumentChunk.project_id == project_id)
            .where(DocumentChunk.text_version < ExtractedText.text_version)
            .group_by(DocumentChunk.document_id)
        )
        return [int(row) for row in self._db.execute(stmt).scalars()]

    # --- 벡터 검색 (RAG-04) --------------------------------------------------

    def _scope_condition(self, project_ids: Sequence[int]):
        """프로젝트 범위 조건을 만든다.

        하나면 등호(=), 여럿이면 IN 으로 낸다.

        원래는 "등호 계획만 검증했으니 흔한 경우가 검증된 계획을 쓰게 한다"는
        이유였다. 그런데 실측(2026-08-18, 청크 6,016개)에서 **둘의 계획이 같았다** —
        양쪽 다 ix_chunk_vec 인덱스 스캔에 Filter 가 붙는다.

            =  : Filter: ((project_id = 1) AND (embedding_model = ...))
            IN : Filter: ((project_id = ANY ('{1,2}')) AND (embedding_model = ...))

        그래서 지금은 나눌 필요가 없다. 그래도 남겨 두는 이유는 두 가지다.
          · 등호가 계획에서 읽기 쉽다 (디버깅할 때 눈에 바로 들어온다)
          · PostgreSQL 이나 pgvector 판이 올라가 둘이 갈리면 흔한 경우가
            영향을 덜 받는다
        """
        if len(project_ids) == 1:
            return DocumentChunk.project_id == project_ids[0]
        return DocumentChunk.project_id.in_(list(project_ids))

    def _apply_scan_settings(self, ef_search: int) -> None:
        """벡터 검색용 세션 파라미터를 이 트랜잭션에만 설정한다.

        SET LOCAL 은 현재 트랜잭션에서만 유효하다. 세션 전체나 다른 요청에
        영향을 주지 않고, 커밋·롤백되면 원래 값으로 돌아간다.

        iterative_scan: pgvector 0.8 부터 있다. 조건 때문에 후보가 모자라면
          인덱스를 더 훑어 온다. strict_order 는 거리 순서를 보장한다
          (relaxed_order 는 더 빠르지만 순서가 약간 어긋날 수 있다).
        ef_search: 한 번에 꺼내 오는 후보 수. 기본 40 은 프로젝트 필터가
          걸린 상황에서 너무 적다.

        Spring 비교: JPA 에 대응물이 없어 EntityManager 로 세션 파라미터를
          직접 실행하는 것에 해당한다.
        """
        self._db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        # ef_search 는 정수로 강제한 뒤 문장에 넣는다. SET 은 바인드 파라미터를
        # 받지 않기 때문이고, int() 를 거치므로 주입 여지가 없다.
        self._db.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))

    def search_by_vector(
        self,
        *,
        project_ids: Sequence[int],
        vector: list[float],
        embedding_model: str,
        limit: int,
        document_id: int | None = None,
        ef_search: int = 100,
    ) -> list[tuple[DocumentChunk, str, int, str, float]]:
        """지정한 프로젝트들 안에서 벡터가 가까운 청크를 찾는다.

        (청크, 문서 파일명, 프로젝트 id, 프로젝트 이름, 코사인 거리) 를 거리
        오름차순으로 돌려준다. 거리는 0 에 가까울수록 비슷하다. 유사도로 바꾸는
        것은 서비스가 한다.

        프로젝트 이름을 조인으로 함께 가져오는 것이 중요하다. 서비스에서
        chunk.document.project.name 으로 접근하면 결과마다 두 단계 지연로딩이
        일어나 N+1 이 된다.

        조건이 두 개인 것도 중요하다.

        1. project_id — "내가 멤버가 아닌 프로젝트는 나오지 않는다"(RAG-04
           판정 기준)를 만족시킨다. 조인이 아니라 document_chunks 자신의 컬럼으로
           거는 이유가 리비전 0014 다.

           HNSW 는 근사 인덱스라서 ef_search 개의 후보를 먼저 만들고 그 다음에
           WHERE 를 적용한다. 그래서 조건이 어느 노드에 붙는지가 갈린다.
             · document_chunks 자신의 컬럼이면 -> HNSW 스캔 노드의 Filter 가 되고,
               살아남은 행이 LIMIT 에 못 미치면 iterative_scan 이 인덱스를 더 훑는다.
             · 조인 조건이면 -> 그 위 노드에서 걸러지므로 HNSW 스캔은 부족한 줄을
               모르고 더 꺼내오지 않는다. 프로젝트가 작을 때 결과가 조용히 적어진다.

           실측(2026-08-18, 청크 6,016개)으로 확인했다.
             = (프로젝트 1, 약 1/3): ix_chunk_vec · Filter · Rows Removed 12 · 3.5ms
             IN (1+2, 약 2/3)     : ix_chunk_vec · Filter · Rows Removed 3  · 4.6ms
             조인 대조군          : Rows Removed by Join Filter 16 (청크 스캔 밖)
           버린 행 수가 선택도에 비례한다 — iterative_scan 이 일하고 있다는 뜻이다.

        2. embedding_model — 이게 없으면 조용히 틀린다. 모델을 바꾸거나 가짜
           임베더로 만든 청크가 섞여 있으면 서로 다른 벡터 공간의 값을 비교하게
           된다. 거리 계산은 에러 없이 성공하고 숫자도 나오지만 그 숫자에 의미가
           없다. ix_chunk_model (embedding_model, document_id) 인덱스가 이 조회용
           으로 만들어져 있다.
        """
        if not project_ids:
            # 멤버십이 없으면 검색할 범위가 없다. 쿼리를 내지 않는다.
            return []

        self._apply_scan_settings(ef_search)

        from app.models.document import Document
        from app.models.project import Project

        distance = DocumentChunk.embedding.cosine_distance(vector).label("distance")
        stmt = (
            select(
                DocumentChunk,
                Document.filename,
                Project.id,
                Project.name,
                distance,
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(Project, Project.id == DocumentChunk.project_id)
            .where(self._scope_condition(project_ids))
            .where(DocumentChunk.embedding_model == embedding_model)
        )
        if document_id is not None:
            stmt = stmt.where(DocumentChunk.document_id == document_id)
        stmt = stmt.order_by(distance).limit(limit)

        return [
            (row[0], row[1], int(row[2]), row[3], float(row[4]))
            for row in self._db.execute(stmt).all()
        ]

    def explain_search(
        self,
        *,
        project_ids: Sequence[int],
        vector: list[float],
        embedding_model: str,
        limit: int,
        ef_search: int = 100,
        summary_only: bool = True,
    ) -> str:
        """위 검색의 실행계획을 문자열로 돌려준다.

        리비전 0014(project_id 역정규화)를 넣은 근거가 "조건이 인덱스 스캔
        단계로 내려간다"는 것인데, 청크가 0행이던 동안에는 확인할 수 없었다.
        운영 코드에서 쓰는 것이 아니라 검증용이다.

        summary_only 가 True 면 판단에 필요한 줄만 남긴다. 계획 전문에는 질의
        벡터 1024개가 그대로 찍혀 화면이 덮인다 — 실제로 한 번 겪었다.
        어느 쪽이든 벡터 리터럴은 마스킹한다.
        """
        if not project_ids:
            return "검색 범위가 비어 있어 계획을 낼 수 없다."

        self._apply_scan_settings(ef_search)

        from app.models.document import Document

        distance = DocumentChunk.embedding.cosine_distance(vector).label("distance")
        stmt = (
            select(DocumentChunk.id, DocumentChunk.seq, Document.filename, distance)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(self._scope_condition(project_ids))
            .where(DocumentChunk.embedding_model == embedding_model)
            .order_by(distance)
            .limit(limit)
        )
        # literal_binds 로 벡터를 문장에 박아 넣는다. EXPLAIN 은 바인드 파라미터를
        # 그대로 받지 못하기 때문이다. 그래서 계획에도 벡터가 찍힌다 -> 아래에서 마스킹.
        compiled = stmt.compile(
            self._db.get_bind(), compile_kwargs={"literal_binds": True}
        )
        rows = self._db.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {compiled}")).all()
        plan = "\n".join(str(r[0]) for r in rows)
        plan = mask_vector_literals(plan)
        return summarize_plan(plan) if summary_only else plan

    # --- 쓰기 ---------------------------------------------------------------

    def delete_for_document(self, document_id: int, *, model: str | None = None) -> int:
        """문서의 청크를 지운다.

        model 을 주면 그 모델로 만든 것만 지운다. 임베딩 모델을 교체할 때
        "옛 모델 청크만 버리고 새로 만든다"를 하려는 것이고, models/chunk.py 의
        ix_chunk_model (embedding_model, document_id) 인덱스가 이 조회용이다.
        """
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        if model is not None:
            stmt = stmt.where(DocumentChunk.embedding_model == model)
        result = self._db.execute(stmt)
        return int(result.rowcount or 0)

    def bulk_insert(self, chunks: list[DocumentChunk]) -> int:
        """청크를 한 번에 넣는다.

        add_all 은 flush 시점에 executemany 로 묶여 나가므로 한 건씩 add 하는
        것보다 왕복이 적다. commit 은 서비스가 한다.
        """
        if not chunks:
            return 0
        self._db.add_all(chunks)
        self._db.flush()
        return len(chunks)
