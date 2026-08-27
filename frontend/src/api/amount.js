// =============================================================================
// 이 파일의 책임: 금액 관련 API 호출을 감싼다. 지금은 과거 유사 사업의 단가 선례
//   조회 하나뿐이다(SRH-002-3).
// 다른 파일과의 관계: api/http.js 의 공통 인스턴스를 쓴다 — 토큰 첨부와 401
//   재발급이 거기 인터셉터에 있다. 응답 필드 이름은 서버와 같은 snake_case 로
//   둔다(프로젝트 합의).
// Spring 비교: RestTemplate 을 감싼 Gateway 클래스에 해당한다.
// =============================================================================

import { http } from './http'

// GET /api/projects/{projectId}/amount-precedents?item_name=특급기술자&limit=20
//
// 찾는 범위는 서버가 정한다 — "내가 멤버인 프로젝트 − 현재 프로젝트" 다.
// 그래서 프런트가 범위를 넘기지 않는다. 의미 검색(POST /api/search)이 범위를
// project_ids 로 받는 것과 다른 점이다.
//
// 응답: {
//   item_name,
//   searched_project_ids: [3, 7],          // 실제로 찾아본 프로젝트
//   summary: { count, min_unit_price, median_unit_price, max_unit_price } | null,
//   precedents: [{ project_id, project_name, document_id, document_filename,
//                  item_name, category, quantity, unit, unit_price, amount,
//                  period_from, period_to, source_quote, decision }]
// }
//
// summary 가 null 인 경우가 있다. 선례가 0건이면 min·median·max 를 낼 수 없어서
// 0 이 아니라 null 로 온다 — 0 을 넣으면 "단가가 0원" 과 구별되지 않는다.
// 화면에서 0 으로 바꾸지 말 것.
//
// 금액은 문자열로 온다(Decimal). 자바스크립트 number 로 바꾸면 조달 금액 크기에서
// 정밀도가 깨질 수 있으므로, 표시할 때만 형식을 입히고 계산은 하지 않는다.
export async function findAmountPrecedents(projectId, { itemName, limit = 20 } = {}) {
  const { data } = await http.get(`/api/projects/${projectId}/amount-precedents`, {
    params: { item_name: itemName, limit },
  })
  return data
}


// GET /api/projects/{projectId}/amount-summary
//
// 프로젝트 금액 현황(AMT-002-2 · AMT-003-2). 계산은 **서버가 다 한다** —
// 화면은 받은 수치를 그대로 그린다.
//
// 응답: {
//   currency: "KRW",
//   item_total, vat_total, total_with_vat,      // 정수(원). 아래 주의 참고
//   by_category: [{ category, amount }],
//   document_count, included_item_count,
//   excluded_no_amount, unverifiable_line_count,
//   line_mismatches: [{ item_id, document_id, filename, item_name,
//                       expected, actual, difference }],
//   included_decisions: ["APPROVED", "EDITED"]
// }
//
// **item_total 에 부가세가 들어 있지 않다.** total_with_vat 가 따로 온다.
// 화면에서 item_total + vat_total 을 더하지 않는다 — 더하면 서버가 이미
// 계산한 값과 두 군데서 같은 규칙을 갖게 되고, 규칙이 바뀌면 한쪽만 틀린다.
// by_category 에는 VAT 행이 **들어 있다**(원가구분별로 다 보여주므로).
// 그래서 by_category 를 합쳐도 item_total 이 되지 않는다. 합치지 않는다.
//
// included_decisions 를 서버가 주는 이유는 화면이 "승인된 항목만 집계됩니다" 를
// 근거 있게 적을 수 있게 하려는 것이다. 화면이 상태 목록을 외우지 않는다.
//
// 선례 조회와 달리 금액이 문자열이 아니라 **정수**로 온다. 서버가 원 단위로
// 반올림해 합계를 내기 때문이다(Decimal 을 그대로 주면 화면이 다시 더해야 한다).
// 그래도 화면에서 계산하지 않는다 — 표시만 한다.
export async function getAmountSummary(projectId) {
  const { data } = await http.get(`/api/projects/${projectId}/amount-summary`)
  return data
}


// GET /api/projects/{projectId}/amount-items?limit=200
//
// 금액 항목 한 줄씩 + **항목별 검산 결과** (AMT-003-3 계산식·산출 근거 표시).
// amount-summary 가 "얼마인가" 를 답하고 이것이 "무엇을 더했는가" 를 답한다.
//
// 응답: {
//   items: [{ id, document_id, filename, item_name, category,
//             quantity, unit, unit_price, amount, currency,
//             source_quote, decision,
//             expected, verified, difference, excluded_reason }],
//   total, returned, truncated, limit, included_decisions
// }
//
// **verified 는 셋이다.** true 맞음 / false 어긋남 / null 검산 불가.
// false 와 null 을 합치면 안 된다 — 제경비·기술료처럼 비율로 산정된 항목은
// 수량·단가가 원래 없어서 null 인데, 묶으면 정상 항목이 틀린 항목으로 보인다.
//
// **수량 × 단가를 화면에서 다시 곱하지 않는다.** expected 가 이미 온다. 서버는
// ROUND_HALF_UP 으로 원 단위에 맞추는데 자바스크립트 부동소수 곱셈은 큰 금액에서
// 1원씩 어긋난다 — 에러 없이 숫자만 틀리는 종류다.
//
// difference = expected - amount 다. **양수면 문서 금액이 작게** 적혀 있다.
// 부호를 그대로 보여주지 않고 문장으로 푼다(화면 쪽 verifyText 참고).
//
// truncated 가 true 면 목록이 상한에서 잘렸고 total 에 전체 건수가 온다.
// 목록 줄 수를 전체 건수로 쓰지 않는다.
//
// 상한을 넘겨 이 함수를 부를 때 limit 을 키우기 전에, 정말 다 보여줄 필요가
// 있는지 생각한다. 서버 최대는 500 이고 그 이상은 422 다.
export async function getAmountItems(projectId, { limit = 200 } = {}) {
  const { data } = await http.get(`/api/projects/${projectId}/amount-items`, {
    params: { limit },
  })
  return data
}


// POST /api/projects/{projectId}/amount-items/{itemId}/task
//
// 검산이 어긋난 금액 항목을 태스크로 만든다 (AMT-004-3 불일치 태스크 제안 ·
// TSK-002-1 AI 제안 승인).
//
// **본문이 없다.** 금액이나 차액을 보내지 않고 항목 id 만 보낸다 — 서버가 그 항목을
// 다시 검산한다. 화면이 낡은 목록을 들고 있으면 이미 고쳐진 항목으로 태스크를 만들
// 수 있고, 그러면 근거 없는 태스크가 남는다.
//
// 제목·설명도 서버가 만든다. 화면마다 문구를 만들면 같은 성격의 태스크가 다르게
// 적히고, 이 태스크는 보드에서도 읽히므로 계산 근거가 설명 안에 있어야 한다.
//
// 응답은 만들어진 태스크(TaskResponse)다. origin='AI_APPROVED' 이고
// source_suggestion_id 가 이 금액 항목 id 다.
//
// 오류를 셋으로 나눠 받는다 — 화면이 할 일이 다르다.
//   404 AMOUNT_ITEM_NOT_FOUND        그 항목이 없다        → 목록을 다시 받는다
//   409 AMOUNT_NOT_MISMATCHED        어긋난 항목이 아니다   → 목록이 낡았다
//   409 AMOUNT_TASK_ALREADY_EXISTS   이미 태스크가 있다     → 목록을 다시 받는다
//
// 세 경우 모두 **목록을 다시 받는 것**이 화면의 할 일이라, 실패해도 invalidate 한다.
export async function createTaskFromMismatch(projectId, itemId) {
  const { data } = await http.post(
    `/api/projects/${projectId}/amount-items/${itemId}/task`,
  )
  return data
}


// PATCH /api/projects/{projectId}/amount-items/{itemId}
//
// 금액 항목을 고친다 (AMT-001-2 금액 항목 승인·수정). 검산이 어긋났을 때 사람이 할
// 수 있는 일이 이것이다.
//
// **보낸 필드만 고친다.** 그래서 changes 에 담긴 키만 보낸다 — 「안 보냈다」와
// 「null 로 보냈다」가 다르다. 앞은 그대로 두라는 뜻이고 뒤는 비우라는 뜻이다.
// 제경비처럼 수량이 원래 없는 항목에서 잘못 채운 값을 지울 수 있어야 한다.
//
// 고칠 수 있는 것은 quantity·unit·unit_price·amount·category 다섯이다.
// item_name·source_quote 는 문서에서 읽은 사실이라 서버가 받지 않는다.
//
// 고치면 decision 이 EDITED 가 된다. PENDING 이던 항목은 이때 합계에 들어온다 —
// 사람이 값을 확인해 고쳤으면 그 자체가 승인이라는 것이 AMT-001-2 다.
//
// **응답이 목록의 한 줄과 같은 모양이다.** 다시 검산한 expected·verified·difference
// 가 함께 오므로 고쳐서 맞게 됐는지 바로 알 수 있다. 화면이 수량×단가를 다시 곱해
// 판단하지 않는다.
export async function updateAmountItem(projectId, itemId, changes) {
  const { data } = await http.patch(
    `/api/projects/${projectId}/amount-items/${itemId}`,
    changes,
  )
  return data
}



// GET /api/projects/{projectId}/amount-items/pending?limit=200
//
// 승인 대기(PENDING) 금액 항목 (AMT-001-2 승인·수정의 대상). getAmountItems 는
// 이미 승인된 것만 주므로, 사람이 승인·거절할 대기 항목은 이 함수로 받는다.
//
// 응답은 getAmountItems 와 **같은 모양**이다 — items[]에 검산 결과
// (expected·verified·difference)가 함께 온다. 승인할지 판단하려면 수량×단가가
// 맞는지 바로 보여야 하기 때문이다. included_decisions 는 ["PENDING"] 이다.
export async function getPendingAmountItems(projectId, { limit = 200 } = {}) {
  const { data } = await http.get(`/api/projects/${projectId}/amount-items/pending`, {
    params: { limit },
  })
  return data
}


// POST /api/projects/{projectId}/amount-items/{itemId}/approve
//
// 대기 항목을 값 그대로 승인한다 (PENDING→APPROVED). 본문 없음 — 항목 id 만 보낸다.
// 값을 고쳐서 승인하는 것은 updateAmountItem(→EDITED)이다. 둘을 나눠야 채택률
// 지표에서 "그대로 쓸 만했는가" 와 "고쳐야 했는가" 를 구분한다.
//
// 응답은 목록의 한 줄과 같은 모양(재검산 포함)이라 화면이 그 줄만 갈아끼울 수 있다.
export async function approveAmountItem(projectId, itemId) {
  const { data } = await http.post(
    `/api/projects/${projectId}/amount-items/${itemId}/approve`,
  )
  return data
}


// POST /api/projects/{projectId}/amount-items/{itemId}/reject
//
// 항목을 거절한다 (→REJECTED). 집계·선례·산출물에서 빠진다. 본문 없음.
// **이미 승인된 항목에도 걸 수 있다** — 잘못 승인한 것을 빼는 「취소」 역할을
// 거절이 겸한다. 되살리려면 다시 approveAmountItem 을 부른다.
export async function rejectAmountItem(projectId, itemId) {
  const { data } = await http.post(
    `/api/projects/${projectId}/amount-items/${itemId}/reject`,
  )
  return data
}



// POST /api/projects/{projectId}/amount-items/{itemId}/cancel
//
// 승인을 취소해 대기(PENDING)로 되돌린다 (APPROVED/EDITED→PENDING). 잘못 승인한
// 항목을 무를 때 쓴다. 거절(reject, 버림)과 달리 「승인 대기」에 다시 나타나
// 승인·거절을 다시 받을 수 있다. decided_by·decided_at 는 서버가 지운다.
export async function cancelAmountItem(projectId, itemId) {
  const { data } = await http.post(
    `/api/projects/${projectId}/amount-items/${itemId}/cancel`,
  )
  return data
}
