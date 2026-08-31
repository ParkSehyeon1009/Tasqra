// =============================================================================
// 이 파일의 책임: 결정사항·일정 제안의 문서별 목록과 승인·수정·거절·취소 API를 감싼다.
// 다른 파일과의 관계: 문서 상세 분석 탭의 DecisionScheduleReviewPanel이 호출하고
//   http.js가 인증·공통 오류 형식을 처리한다. snake_case 응답은 그대로 유지한다.
// Spring 비교: RestTemplate/WebClient를 감싼 화면 전용 Gateway다.
// =============================================================================

import { http } from './http'

async function getList(projectId, resource, state, { limit = 200, documentId } = {}) {
  const suffix = state ? `/${state}` : ''
  const params = { limit }
  if (documentId !== undefined && documentId !== null) params.document_id = documentId
  const { data } = await http.get(`/api/projects/${projectId}/${resource}${suffix}`, {
    params,
  })
  return data
}

async function postAction(projectId, resource, itemId, action) {
  const { data } = await http.post(
    `/api/projects/${projectId}/${resource}/${itemId}/${action}`,
  )
  return data
}

async function patchItem(projectId, resource, itemId, changes) {
  const { data } = await http.patch(
    `/api/projects/${projectId}/${resource}/${itemId}`,
    changes,
  )
  return data
}

export const getDecisions = (projectId, options) =>
  getList(projectId, 'decisions', '', options)
export const getPendingDecisions = (projectId, options) =>
  getList(projectId, 'decisions', 'pending', options)
export const getRejectedDecisions = (projectId, options) =>
  getList(projectId, 'decisions', 'rejected', options)
export const approveDecision = (projectId, itemId) =>
  postAction(projectId, 'decisions', itemId, 'approve')
export const rejectDecision = (projectId, itemId) =>
  postAction(projectId, 'decisions', itemId, 'reject')
export const cancelDecision = (projectId, itemId) =>
  postAction(projectId, 'decisions', itemId, 'cancel')
export const updateDecision = (projectId, itemId, changes) =>
  patchItem(projectId, 'decisions', itemId, changes)

export const getScheduleItems = (projectId, options) =>
  getList(projectId, 'schedule-items', '', options)
export const getPendingScheduleItems = (projectId, options) =>
  getList(projectId, 'schedule-items', 'pending', options)
export const getRejectedScheduleItems = (projectId, options) =>
  getList(projectId, 'schedule-items', 'rejected', options)
export const approveScheduleItem = (projectId, itemId) =>
  postAction(projectId, 'schedule-items', itemId, 'approve')
export const rejectScheduleItem = (projectId, itemId) =>
  postAction(projectId, 'schedule-items', itemId, 'reject')
export const cancelScheduleItem = (projectId, itemId) =>
  postAction(projectId, 'schedule-items', itemId, 'cancel')
export const updateScheduleItem = (projectId, itemId, changes) =>
  patchItem(projectId, 'schedule-items', itemId, changes)
