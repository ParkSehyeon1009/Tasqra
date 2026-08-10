// =============================================================================
// 이 파일의 책임: 화면에 값을 표시할 때 쓰는 순수 변환 함수들. 날짜·숫자 형식을
//   한 곳에서 정해서, 목록과 상세에서 같은 값이 다르게 보이는 일을 막는다.
// 다른 파일과의 관계: components/DocumentDetail.jsx, pages/ListPage.jsx 에서
//   사용한다. React 나 API 에 의존하지 않는 순수 함수만 둔다.
// Spring 비교: 공용 Formatter / Utils 클래스에 해당. 상태를 갖지 않는다.
// =============================================================================

/** ISO 문자열을 "2026-08-03 14:05" 형태로 바�ാ꾼다. */
export function formatDateTime(value) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '-'

  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    ` ${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

/** 목록 표에서 쓸 짧은 형태 "08-03 14:05". */
export function formatDateShort(value) {
  const full = formatDateTime(value)
  return full === '-' ? '-' : full.slice(5)
}

/** 1234 -> "1,234". null 이면 "-". */
export function formatNumber(value) {
  if (value === null || value === undefined) return '-'
  return value.toLocaleString('ko-KR')
}

/** 응답 시간(ms)을 사람이 읽기 쉽게. 1200 -> "1.2초" */
export function formatLatency(ms) {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}초`
}
