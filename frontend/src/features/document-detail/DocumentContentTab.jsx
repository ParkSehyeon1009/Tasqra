import { useMemo, useRef, useState } from 'react'

export default function DocumentContentTab({ document }) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const marksRef = useRef(null)
  const parts = useMemo(() => splitText(document.extracted_text ?? '', query), [document.extracted_text, query])
  const matchCount = parts.filter(part => part.match).length
  function move(delta) {
    if (!matchCount) return
    const next = (activeIndex + delta + matchCount) % matchCount
    setActiveIndex(next)
    requestAnimationFrame(() => marksRef.current?.querySelectorAll('mark')[next]?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }
  function changeQuery(value) { setQuery(value); setActiveIndex(0) }
  async function copyText() { await navigator.clipboard.writeText(document.extracted_text ?? '') }
  let matchIndex = -1
  return <section className="detail-card content-tab"><header><div><h2>추출된 문서 내용</h2><p>텍스트 버전 v{document.text_version ?? 1} · {document.is_confirmed ? '검수 확정됨' : '확정 전'}</p></div><button onClick={copyText}>전체 복사</button></header>
    <div className="document-search"><input type="search" value={query} onChange={event => changeQuery(event.target.value)} placeholder="문서 내용에서 검색"/><span>{matchCount ? `${activeIndex + 1} / ${matchCount}` : '0개'}</span><button disabled={!matchCount} onClick={() => move(-1)}>↑</button><button disabled={!matchCount} onClick={() => move(1)}>↓</button></div>
    <div className="document-text" ref={marksRef}>{document.extracted_text ? parts.map((part, index) => { if (part.match) matchIndex += 1; return part.match ? <mark className={matchIndex === activeIndex ? 'active' : ''} key={index}>{part.text}</mark> : <span key={index}>{part.text}</span> }) : <p className="detail-empty">추출된 텍스트가 없습니다.</p>}</div>
  </section>
}

function splitText(text, query) {
  if (!query.trim()) return [{ text, match: false }]
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.split(new RegExp(`(${escaped})`, 'gi')).filter(Boolean).map(part => ({ text: part, match: part.toLowerCase() === query.toLowerCase() }))
}
