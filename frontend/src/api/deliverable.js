// =============================================================================
// 이 파일의 책임: 산출물 API(DLV-001-2) 호출을 감싼다. 화면(DeliverablesView)은
//   axios 나 경로를 모르고 이 함수만 부른다.
// 다른 파일과의 관계: api/http.js 의 공통 인스턴스를 쓴다 — 토큰 첨부와 401
//   재발급이 거기 인터셉터에 있다. 응답 필드 이름은 서버와 같은 snake_case
//   그대로 둔다(프로젝트 합의).
// Spring 비교: RestTemplate 을 감싼 Gateway 클래스에 해당한다.
// =============================================================================

import { http } from './http'

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
//     documents, decisions, schedule_items, amount_items,   // 담기는 것
//     pending_suggestions,      // 담기지 않는다. 처리해야 할 일이다
//     completed_tasks,          // null 이면 "아직 셀 수 없다" (0 건이 아니다)
//   },
//   can_generate,               // false 면 만들 수 없다
//   blocked_reason,             // 그 이유. 화면이 그대로 보여줄 수 있는 문장이다
//   needs_period,               // 이 유형이 기간을 쓰는가
//   uncountable: ['completed_tasks'],   // 셀 수 없는 재료의 이름
// }
//
// ⚠️ completed_tasks 가 null 인 이유: 세려면 tasks 테이블이 필요한데 아직 없다
//   (TSK-001-1 태스크 CRUD 미구현). **화면에서 0 으로 바꾸지 말 것** — 사용자가
//   "이번 주에 완료한 일이 없다" 로 잘못 읽는다. 대시보드의 open_tasks 와 같은
//   규칙이다. 어느 항목이 그런지는 응답의 uncountable 이 알려주므로 화면이
//   필드 이름을 외우지 않아도 된다.
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
