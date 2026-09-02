// =============================================================================
// 이 파일의 책임: 같은 프로젝트가 어느 화면에서나 같은 색 표식을 갖게 한다.
// 다른 파일과의 관계: ProjectSidebar와 PortfolioDashboard가 같은 클래스 번호를 쓴다.
// Spring 비교: 프로젝트 ID를 표현용 색 토큰으로 바꾸는 순수 View Mapper다.
// =============================================================================

const PROJECT_COLOR_COUNT = 5

export function projectColorIndex(projectId) {
  const value = String(projectId ?? '')
  let hash = 0
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0
  }
  return hash % PROJECT_COLOR_COUNT
}
