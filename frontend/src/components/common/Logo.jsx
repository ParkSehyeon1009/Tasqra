// =============================================================================
// 이 파일의 책임: Tasqra 로고 마크와 워드마크를 공통으로 그린다.
// 다른 파일과의 관계: 공용 헤더·인증 화면과 프로젝트 사이드바가 같은 로고 자산을 사용한다.
// Spring 비교: 여러 화면이 공유하는 재사용 View Component다.
// =============================================================================

export function BrandMark({ className = 'logo-mark', size = 36 }) {
  return <img className={className} src="/tasqra-logo.png" width={size} height={size} alt="" aria-hidden="true" draggable="false"/>
}

export default function Logo() {
  return <div className="logo"><BrandMark/><strong>Tasqra</strong></div>
}
