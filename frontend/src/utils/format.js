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


/** Numeric 문자열에 천 단위 구분을 넣고 뜻 없는 소수점 뒤 0 을 뗀다.
 *
 *   "9500000.00" -> "9,500,000"      (금액 · Numeric(18,2))
 *   "3.0000"     -> "3"              (수량 · Numeric(18,4))
 *   "2.5000"     -> "2.5"
 *
 * 금액만이 아니라 **수량에도 쓴다.** 수량을 그대로 뿌리면 "3.0000" 이 화면에서
 * 3000 으로 읽힌다 — 실제로 그렇게 읽은 일이 있었다.
 *
 * formatNumber 를 쓰지 않는 이유
 *   서버가 금액을 **문자열**로 보낸다(Numeric = Decimal). 문자열에
 *   toLocaleString 을 부르면 그 문자열이 그대로 돌아와 쉼표가 붙지 않는다.
 *   Number 로 바꾸면 쉼표는 붙지만 조달 금액 크기에서 정밀도가 깨질 수 있다
 *   (백엔드가 float 대신 Numeric 을 쓰는 것과 같은 이유다).
 *   그래서 숫자로 바꾸지 않고 문자열을 직접 자른다.
 *
 * 소수부가 .00 이면 떼고, 값이 있으면 남긴다. 조달 금액은 원 단위라 보통 .00 이다.
 */
export function formatMoney(value) {
  if (value === null || value === undefined || value === '') return '-'
  const text = String(value).trim()
  const negative = text.startsWith('-')
  const [whole, fraction] = text.replace(/^-/, '').split('.')
  if (!/^\d+$/.test(whole)) return text
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const tail = fraction && /[1-9]/.test(fraction) ? '.' + fraction.replace(/0+$/, '') : ''
  return (negative ? '-' : '') + grouped + tail
}
