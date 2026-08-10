// =============================================================================
// 이 파일의 책임: API 응답을 기다리는 동안 보여줄 로딩 표시.
// 다른 파일과의 관계: pages/ListPage.jsx, pages/DetailPage.jsx 에서 사용한다.
// label 을 넘기면 스피너 아래에 안내 문구를 함께 보여준다.
// =============================================================================

import './Spinner.css'

export default function Spinner({ label, inline = false }) {
  return (
    <div className={inline ? 'spinner-wrap spinner-wrap--inline' : 'spinner-wrap'}>
      {/* 스크린리더가 장식용 원을 읽지 않도록 aria-hidden 처리 */}
      <span className="spinner" aria-hidden="true" />
      {/* role=status: 로딩 완료 시 스크린리더가 변경을 알린다 */}
      {label && <span className="spinner-label" role="status">{label}</span>}
    </div>
  )
}
