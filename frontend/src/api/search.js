// =============================================================================
// 이 파일의 책임: 의미 검색 API(RAG-04 = SRH-001) 호출을 감싼다.
//   화면(SearchView)은 axios 나 경로를 모르고 이 함수만 부른다.
// 다른 파일과의 관계: api/http.js 의 공통 인스턴스를 쓴다 — 토큰 첨부와
//   401 재발급이 거기 인터셉터에 있다. 응답 필드 이름은 서버와 같은
//   snake_case 그대로 둔다 (프로젝트 합의).
// Spring 비교: @FeignClient 나 RestTemplate 을 감싼 Gateway 클래스에 해당한다.
// =============================================================================

import { http } from './http'

// POST /api/search — 의미 검색
//
// 경로에 projectId 가 없는 것에 주의한다. 검색 범위가 "내가 멤버인 프로젝트
// 전체"일 수 있어서, 범위를 본문의 project_ids 로 받는다.
//   projectIds = null      -> 내가 멤버인 모든 프로젝트
//   projectIds = [3]       -> 그 프로젝트만
//   projectIds = [3, 7]    -> 골라서 몇 개
//
// GET 이 아닌 이유: 질의가 문장이라 URL 이 길어지고, 범위가 배열이며,
// 검색어가 브라우저 이력과 접근 로그에 남지 않아야 한다(조달 문서라
// "무엇을 찾는지"가 사업 정보다).
//
// 응답: {
//   query, searched_project_ids, embedding_model, took_ms, total,
//   results: [{ chunk_id, document_id, document_filename, project_id,
//               project_name, seq, page_number, similarity, snippet,
//               char_count, content_start, content_end }]
// }
export async function searchDocuments({ query, projectIds = null, limit = 10, documentId = null, minSimilarity = null } = {}) {
  const body = { query, limit }
  // null 을 명시적으로 보내지 않는다. 서버 기본값이 "전체 범위"이고,
  // project_ids: [] 는 스키마가 거부한다(전체를 원하면 필드를 생략한다).
  if (Array.isArray(projectIds) && projectIds.length > 0) body.project_ids = projectIds
  if (documentId) body.document_id = documentId
  if (minSimilarity !== null && minSimilarity !== undefined) body.min_similarity = minSimilarity

  const { data } = await http.post('/api/search', body)
  return data
}

// POST /api/search/explain — 실행계획 (검증용 · 임시)
//
// 리비전 0014(document_chunks.project_id 역정규화)를 넣은 근거를 눈으로
// 확인하려고 만든 것이다. 운영 화면에서는 쓰지 않는다.
export async function explainSearch({ query, projectIds = null, limit = 5 } = {}) {
  const body = { query, limit }
  if (Array.isArray(projectIds) && projectIds.length > 0) body.project_ids = projectIds
  const { data } = await http.post('/api/search/explain', body)
  return data.plan
}

// 개발용 가짜 임베더가 쓰는 모델 이름. 이 값이 오면 벡터에 의미가 없으므로
// 화면에 그 사실을 알려야 한다 — 아니면 "검색이 왜 이상하지"로 시간을 버린다.
export const FAKE_EMBEDDING_MODEL = 'fake-hash-v1'
