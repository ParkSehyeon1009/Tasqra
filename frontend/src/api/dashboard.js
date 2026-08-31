// =============================================================================
// 이 파일의 책임: 프로젝트 핵심 현황과 프로젝트 캘린더 API 호출을 감싼다.
//   화면은 axios나 URL 계약을 모르고 이 파일의 함수만 부른다.
// 다른 파일과의 관계: api/http.js 의 공통 인스턴스를 쓴다 — 토큰 첨부와 401
//   재발급이 거기 인터셉터에 있다. 응답 필드 이름은 서버와 같은 snake_case
//   그대로 둔다(프로젝트 합의).
// Spring 비교: RestTemplate 을 감싼 Gateway 클래스에 해당한다.
// =============================================================================

import { http } from './http'

// GET /api/projects/{projectId}/dashboard
//
// 지표를 화면에서 세지 않고 서버에서 받는 이유
//   전에는 문서 목록을 받아 화면에서 셌다. 그런데 그 목록은 GET /documents 의
//   첫 페이지이고 기본 size 가 20 이다. 그래서 문서가 21건 이상인 프로젝트에서
//   "처리 중 3건" 같은 숫자가 조용히 틀렸다 — 에러도 안 나고 화면도 정상으로
//   보인다. 세는 일은 DB 가 한다.
//
// 응답: {
//   documents: { total, processing, extracted, completed, failed },
//   review_pending,            // OCR 검수가 필요한 문서 수
//   pending_amount_items,      // 승인 대기 금액 항목 수
//   open_tasks,                // 완료되지 않은 태스크 수
//   document_types: [{ document_type, count }],   // document_type: null = 미분류
//   recent_documents: [{ id, filename, file_type, document_type,
//                        status, review_status, created_at }]
// }
//
export async function getDashboard(projectId, { recentLimit = 5 } = {}) {
  const { data } = await http.get(`/api/projects/${projectId}/dashboard`, {
    params: { recent_limit: recentLimit },
  })
  return data
}

// 태스크 마감과 승인된 일정의 통합 월간 조회. from/to는 달력 그리드의 양 끝이다.
export async function getDashboardCalendar(projectId, { from, to }) {
  const { data } = await http.get(`/api/projects/${projectId}/dashboard/calendar`, {
    params: { from, to },
  })
  return data
}
