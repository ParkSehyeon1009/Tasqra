// =============================================================================
// 이 파일의 책임: 산출물 API(DLV-001-2) 호출을 감싼다. 화면(DeliverablesView)은
//   axios 나 경로를 모르고 이 함수만 부른다.
// 다른 파일과의 관계: api/http.js 의 공통 인스턴스를 쓴다 — 토큰 첨부와 401
//   재발급이 거기 인터셉터에 있다. 응답 필드 이름은 서버와 같은 snake_case
//   그대로 둔다(프로젝트 합의).
// Spring 비교: RestTemplate 을 감싼 Gateway 클래스에 해당한다.
// =============================================================================

import { http } from './http'
import { parseFilename, triggerBrowserDownload } from '../utils/download'

// GET /api/projects/{projectId}/deliverables/preview
//
// 무엇을 위한 것인가
//   산출물에 담길 내용이 몇 건인지 **AI 를 부르기 전에** 세어 돌려준다.
//   빈 보고서를 만들고 나서야 비어 있음을 아는 것과, 만들기 전에 아는 것의
//   차이다. LLM 호출은 되돌릴 수 없는 비용이다.
//
// 응답: {
//   kind, period_from, period_to,
//   counts: {
//     documents, completed_tasks, decisions, schedule_items, amount_items,  // 담기는 것
//     pending_suggestions,      // 담기지 않는다. 처리해야 할 일이다
//   },
//   can_generate,               // false 면 만들 수 없다
//   blocked_reason,             // 그 이유. 화면이 그대로 보여줄 수 있는 문장이다
//   needs_period,               // 이 유형이 기간을 쓰는가
//   uncountable: [],            // 셀 수 없는 재료의 이름. 지금은 비어 있다
// }
//
// completed_tasks 는 이제 실제 건수다
//   전에는 tasks 테이블이 없어 null 이었다. 리비전 0019 로 테이블이 생겨 세므로
//   0 은 "집계 전" 이 아니라 그 기간에 끝낸 일이 없다는 뜻이다.
//   **uncountable 처리는 지우지 않는다** — 다음에 또 못 세는 재료가 생기면
//   서버가 그 이름을 담아 보내고 화면은 고치지 않아도 된다. 화면이 필드 이름을
//   외우지 않게 하려고 둔 장치다.
//
// can_generate 를 화면이 계산하지 않는 이유
//   건수를 보고 화면이 스스로 판단하면 같은 규칙이 서버와 화면 두 곳에 생긴다.
//   승인 대기는 건수에 있지만 생성 가능 판정에는 **더하지 않는다** 같은 규칙이
//   섞여 있어서, 화면에서 다시 구현하면 조용히 어긋난다.
//
// 기간을 언제 보내는가
//   유형과 상관없이 늘 보낸다. 서버가 기간을 쓰지 않는 유형에서는 **무시**하므로
//   (주간 보고서만 필수) 화면이 "어느 유형이 기간을 쓰는지" 를 알 필요가 없다.
//   그 규칙은 DB CHECK 와 서비스에 이미 있고, 화면에 또 두면 세 곳이 된다.
export async function getDeliverablePreview(projectId, { kind, periodFrom, periodTo }) {
  const { data } = await http.get(`/api/projects/${projectId}/deliverables/preview`, {
    params: { kind, period_from: periodFrom, period_to: periodTo },
  })
  return data
}



// POST /api/projects/{projectId}/deliverables — 산출물 만들기 (DLV-002-x)
//
// `format` 에 기본값을 두지 않는다. 고르지 않으면 서버가 422 를 낸다 —
// 화면도 버튼을 막지만 서버가 마지막 관문이다(DLV-001-1 완료 판정).
//
// 오류를 화면이 그대로 보여줄 수 있다
//   422 DELIVERABLE_EMPTY            담을 내용이 없다. message 에 이유가 있다
//   501 DELIVERABLE_FORMAT_NOT_READY 값은 맞지만 아직 못 만드는 형식이다
//   403 PROJECT_FORBIDDEN            VIEWER 는 만들 수 없다
// http.js 의 인터셉터가 message·code 를 Error 에 담아 주므로 여기서 손대지 않는다.
export async function createDeliverable(projectId, { kind, format, periodFrom, periodTo }) {
  const { data } = await http.post(`/api/projects/${projectId}/deliverables`, {
    kind,
    format,
    period_from: periodFrom,
    period_to: periodTo,
  })
  return data
}

// GET /api/projects/{projectId}/deliverables — 생성 이력 (DLV-003-3)
//
// 최근에 만든 것이 먼저 온다. 각 건에 `is_stale` 과 `stale_changes` 가 있다 —
// 만든 뒤 재료가 늘었는지다(DLV-003-4). `stale_changes` 는 **늘어난 것만** 담는다.
export async function listDeliverables(projectId) {
  return (await http.get(`/api/projects/${projectId}/deliverables`)).data
}

// 산출물 파일 받기 (DLV-003-3)
//
// **경로를 조립하지 않고 목록이 준 `download_url` 을 그대로 쓴다.** 서버가 그
// 목적으로 응답에 담아 준다(DeliverableResponse.download_url). 조립하면 서버가
// 경로를 바꿀 때 화면이 조용히 404 를 받는다. api/document.js 의
// getOcrPageImage 도 같은 방식이다.
//
// 파일 이름도 서버가 정한다 — Content-Disposition 에 제목으로 만든 이름이 온다.
// 확장자와 MIME 이 한 곳(서버)에서만 결정된다.
//
// 이력에는 있는데 파일이 사라지면 410 이다. 404(그 산출물이 없다)와 구분된다.
export async function downloadDeliverable(downloadUrl, fallbackName) {
  const response = await http.get(downloadUrl, { responseType: 'blob' })
  const filename = parseFilename(response.headers['content-disposition'], fallbackName)
  triggerBrowserDownload(response.data, filename)
  return filename
}

// DELETE /api/projects/{projectId}/deliverables/{id} — 이력과 파일 삭제
export async function deleteDeliverable(projectId, deliverableId) {
  await http.delete(`/api/projects/${projectId}/deliverables/${deliverableId}`)
}
