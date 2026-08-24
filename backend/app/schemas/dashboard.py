# =============================================================================
# 이 파일의 책임: 프로젝트 핵심 현황(DSH-001) 응답 계약이다. 대시보드가 보여줄
#   지표와 최근 문서 목록의 모양을 정한다.
# 다른 파일과의 관계: services/dashboard_service.py 가 이 모델을 채워 돌려주고
#   api/routes/dashboard_router.py 가 response_model 로 쓴다. 최근 문서 항목은
#   models/document.py 의 Document 에서 그대로 만든다(from_attributes).
# Spring 비교: 응답 DTO 다. ConfigDict(from_attributes=True) 는 엔티티에서 DTO 를
#   만드는 MapStruct 매핑이나 생성자 프로젝션에 해당한다.
#
# DSH-001 이 요구하는 지표는 여섯이다 — 문서 수 · 처리 중 문서 · 열린 태스크 ·
# 승인 대기 · 문서 유형 분포 · 최근 문서. 열린 태스크는 tasks 테이블에서
# status가 DONE이 아닌 항목을 센다.
#
#   승인 대기      amount_items 만 센다. 그래서 이름이 pending_amount_items 이고
#                 pending_suggestions 가 아니다. 같은 승인 대기인 decisions ·
#                 schedule_items 는 모델이 없어 빠져 있는데, 이름을 뭉뚱그리면
#                 나중에 그 둘이 연결됐을 때 "이미 다 세고 있었다" 고 착각하게
#                 된다. 세는 대상을 이름에 박아 둔다.
# =============================================================================

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DashboardDocumentCounts(BaseModel):
    """문서 수와 상태별 내역.

    total 은 상태별 합이다. 상태 분포를 한 번 조회해서 더하므로 총계를 위한
    COUNT 조회를 따로 내지 않는다 — 두 조회로 나누면 그 사이에 문서가 늘어
    "총계 11, 상태별 합 10" 처럼 어긋날 수 있다.

    processing 은 PENDING · EXTRACTING · ANALYZING 을 합한 값이다. 화면이
    이미 그 셋을 "처리 중" 으로 묶어 왔고(utils/documentStatus.js 의
    getDocumentPrimaryAction 도 같은 셋을 쓴다) 같은 기준을 서버에도 둔다.

    failed 를 따로 두는 이유는 사용자가 손을 써야 하는 유일한 상태이기 때문이다.
    처리 중에 섞으면 기다리면 끝나는 것처럼 보인다.
    """

    total: int
    processing: int
    extracted: int
    completed: int
    failed: int


class DashboardDocumentTypeCount(BaseModel):
    """문서 유형 분포 한 칸.

    document_type 이 None 인 칸은 "아직 유형이 정해지지 않은 문서" 다.
    documents.document_type 이 nullable 이라 실제로 생긴다(업로드할 때 유형을
    고르지 않으면 비어 있고, AI 분류가 채우기 전까지 NULL 이다). 이 칸을 빼면
    분포의 합이 문서 수와 맞지 않아 사용자가 숫자를 믿지 못한다.
    """

    document_type: str | None
    count: int


class DashboardRecentDocument(BaseModel):
    """최근 문서 한 줄. Document 엔티티에서 그대로 만든다.

    상태와 검수 상태를 함께 주는 이유는 화면이 배지 두 개를 그리기 때문이다
    (기존 DashboardView 의 RecentDocument 가 그렇게 하고 있다). id 는 문서
    상세로 이동하는 데 쓴다 — DSH-001 완료 판정의 "관련 화면으로 이동" 부분이다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    document_type: str | None
    status: str
    review_status: str
    created_at: datetime


class DashboardResponse(BaseModel):
    documents: DashboardDocumentCounts
    # OCR 검수가 필요한 문서 수. review_status 가 PENDING 또는 IN_PROGRESS 다.
    # DSH-001 목록에는 없지만 기존 대시보드가 이미 보여주던 지표라서 함께 낸다.
    # 화면에서 세던 것을 서버로 옮기는 것이 이 작업의 요점이므로, 옮기면서
    # 빠뜨리면 되던 것이 사라진다.
    review_pending: int
    # 승인 대기 금액 항목 수. amount_items.decision = 'PENDING'.
    # ix_amount_pending 부분 인덱스가 바로 이 조회를 위해 있다(리비전 0007).
    pending_amount_items: int
    # 완료되지 않은 TODO · IN_PROGRESS 태스크 수.
    open_tasks: int
    document_types: list[DashboardDocumentTypeCount] = Field(default_factory=list)
    recent_documents: list[DashboardRecentDocument] = Field(default_factory=list)
