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
