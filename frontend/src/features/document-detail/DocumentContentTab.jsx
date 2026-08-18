import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

// 추가된 것: URL 의 ?from=&to= 로 원문 한 구간을 강조하고 그 자리로 스크롤한다.
// 의미 검색 결과에서 조각을 누르면 그 조각이 원문의 어디인지 보여주기 위한 것이다.
// 좌표는 extracted_texts.content 안의 [from, to) 이고, 이 화면이 그리는
// document.extracted_text 가 바로 그 문자열이다(document_router 가 extracted.
// content 를 그대로 담는다). 그래서 slice 로 바로 잘라 쓸 수 있다.
// 파라미터가 없으면 기존 동작과 완전히 같다.
export default function DocumentContentTab({ document }) {
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const marksRef = useRef(null)
  const text = document.extracted_text ?? ''
  const range = useMemo(() => parseRange(params.get('from'), params.get('to'), text.length), [params, text.length])
  // 직접 입력한 검색어가 있으면 그쪽을 우선한다. 구간 강조는 "어디서 왔는지"를
  // 알려주는 것이고, 검색어는 지금 찾으려는 것이라 더 새로운 의도다.
  const mode = query.trim() ? 'keyword' : range ? 'range' : 'plain'
  const parts = useMemo(() => {
    if (mode === 'keyword') return splitText(text, query)
    if (mode === 'range') return splitRange(text, range.from, range.to)
    return [{ text, match: false }]
  }, [text, query, mode, range])
  const matchCount = mode === 'keyword' ? parts.filter(part => part.match).length : 0
  function move(delta) {
    if (!matchCount) return
    const next = (activeIndex + delta + matchCount) % matchCount
    setActiveIndex(next)
    requestAnimationFrame(() => marksRef.current?.querySelectorAll('mark')[next]?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }
  function changeQuery(value) { setQuery(value); setActiveIndex(0) }
  function clearRange() {
    // tab 은 남겨야 한다. 통째로 비우면 다른 탭으로 튄다.
    setParams({ tab: 'content' }, { replace: true })
  }
  async function copyText() { await navigator.clipboard.writeText(text) }
  // 구간 강조로 들어왔을 때 그 자리로 한 번 스크롤한다. 문서가 길면 강조만
  // 해 두어도 화면 밖에 있어서 보이지 않는다.
  useEffect(() => {
    if (mode !== 'range') return
    const target = marksRef.current?.querySelector('mark')
    if (!target) return
    const frame = requestAnimationFrame(() => target.scrollIntoView({ behavior: 'smooth', block: 'center' }))
    return () => cancelAnimationFrame(frame)
  }, [mode, range, text])
  let matchIndex = -1
  return <section className="detail-card content-tab"><header><div><h2>추출된 문서 내용</h2><p>텍스트 버전 v{document.text_version ?? 1} · {document.is_confirmed ? '검수 확정됨' : '확정 전'}</p></div><button onClick={copyText}>전체 복사</button></header>
    {range && <div className="content-range-notice"><span>검색에서 고른 조각을 원문에서 강조했습니다. ({range.from.toLocaleString()}~{range.to.toLocaleString()}자)</span><button onClick={clearRange}>강조 해제</button></div>}
    <div className="document-search"><input type="search" value={query} onChange={event => changeQuery(event.target.value)} placeholder="문서 내용에서 검색"/><span>{mode === 'range' ? '조각 1곳' : matchCount ? `${activeIndex + 1} / ${matchCount}` : '0개'}</span><button disabled={!matchCount} onClick={() => move(-1)}>↑</button><button disabled={!matchCount} onClick={() => move(1)}>↓</button></div>
    <div className="document-text" ref={marksRef}>{text ? parts.map((part, index) => { if (part.match) matchIndex += 1; return part.match ? <mark className={mode === 'range' ? 'range' : matchIndex === activeIndex ? 'active' : ''} key={index}>{part.text}</mark> : <span key={index}>{part.text}</span> }) : <p className="detail-empty">추출된 텍스트가 없습니다.</p>}</div>
  </section>
}

function splitText(text, query) {
  if (!query.trim()) return [{ text, match: false }]
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.split(new RegExp(`(${escaped})`, 'gi')).filter(Boolean).map(part => ({ text: part, match: part.toLowerCase() === query.toLowerCase() }))
}

// 원문을 [from, to) 하나만 강조하도록 세 조각으로 나눈다.
function splitRange(text, from, to) {
  const parts = []
  if (from > 0) parts.push({ text: text.slice(0, from), match: false })
  parts.push({ text: text.slice(from, to), match: true })
  if (to < text.length) parts.push({ text: text.slice(to), match: false })
  return parts
}

/**
 * ?from=&to= 를 읽는다. 믿을 수 없는 값이면 null 을 준다 — 강조를 안 하는 것이
 * 엉뚱한 곳을 강조하는 것보다 낫다.
 *
 * 검수로 원문이 바뀌면 청킹 당시의 좌표가 어긋날 수 있다. 길이를 벗어난 경우는
 * 여기서 걸러지지만, 길이 안에서 내용만 바뀐 경우는 알 수 없다. 검색 응답에
 * text_version 이 없어서 대조할 수가 없다(넣으면 정확히 걸러낼 수 있다).
 */
function parseRange(rawFrom, rawTo, length) {
  if (rawFrom === null || rawTo === null) return null
  if (!rawFrom.trim() || !rawTo.trim()) return null
  const from = Number(rawFrom)
  const to = Number(rawTo)
  if (!Number.isInteger(from) || !Number.isInteger(to)) return null
  if (from < 0 || to <= from || to > length) return null
  return { from, to }
}
