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
