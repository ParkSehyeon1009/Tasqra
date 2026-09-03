// =============================================================================
// 이 파일의 책임: 단일 프로젝트 문서 질의응답(CHAT-001) API 호출을 감싼다.
// 다른 파일과의 관계: ChatView는 axios와 URL을 모르고 이 함수만 사용하며,
//   http.js가 인증 토큰·재발급·공통 오류 형식을 처리한다.
// Spring 비교: 프로젝트 챗봇 REST endpoint를 감싼 프런트 Gateway다.
// =============================================================================

import { http } from './http'

export async function askProjectDocuments(projectId, question) {
  const { data } = await http.post(`/api/projects/${projectId}/chat`, { question })
  return data
}
