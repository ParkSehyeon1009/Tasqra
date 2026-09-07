// =============================================================================
// 이 파일의 책임: 문서의 최신 요약·분류와 과거 분석 이력을 보여준다.
// 다른 파일과의 관계: DocumentDetailPage의 분석 결과 왼쪽 영역으로 조립되며,
//   긴 최신 결과는 접어서 오른쪽 액션 아이템과 한 화면에서 비교하게 한다.
// Spring 비교: 분석 결과 DTO를 표시하는 MVC View이며 재분석·다운로드 이벤트는
//   상위 Controller 역할의 DocumentDetailPage에 위임한다.
// =============================================================================

import { useEffect, useMemo, useRef, useState } from 'react'
import { getAnalysisCategoryLabel } from '../../utils/analysisCategory'

const TRAIT_LABELS = {
  COST_DETAILS: '금액 내역 포함',
  SCHEDULE: '일정 포함',
  CONTRACT_TERMS: '계약 조건 포함',
  DECISION_RECORD: '결정 기록 포함',
  ACTION_ITEMS: '후속 업무 포함',
}

export default function DocumentAnalysisTab({ document, canAnalyze, analyzing, onAnalyze, downloading, onDownload }) {
  const [historyType, setHistoryType] = useState(null)
  const grouped = useMemo(() => groupAnalyses(document.analyses ?? []), [document.analyses])
  const latest = [grouped.summary?.[0], grouped.category?.[0]].filter(Boolean)
  if (!latest.length) return <section className="detail-card analysis-empty"><span>✦</span><h2>아직 분석 결과가 없습니다.</h2><p>{document.review_status === 'PENDING' ? 'OCR 검수를 완료한 후 분석하는 것을 권장합니다.' : '현재 문서 텍스트를 요약하고 분류할 수 있습니다.'}</p>{canAnalyze && <button className="primary" disabled={analyzing} onClick={onAnalyze}>{analyzing ? '분석 중...' : '문서 분석 실행'}</button>}</section>
  return <div className="analysis-results">
    <div className="analysis-toolbar"><div><strong>최신 분석 결과</strong><span>현재 표시된 요약과 분류를 내려받을 수 있습니다.</span></div><button disabled={downloading} onClick={onDownload}>{downloading ? '파일 생성 중...' : '요약·분류 다운로드'}</button></div>
    {latest.map(item => <AnalysisCard key={item.id} analysis={item} textVersion={document.text_version}/>) }
    <div className="analysis-footer-actions">{(grouped.summary?.length ?? 0) > 1 && <button onClick={() => setHistoryType(historyType === 'summary' ? null : 'summary')}>과거 요약 기록 {historyType === 'summary' ? '닫기' : '보기'}</button>}{(grouped.category?.length ?? 0) > 1 && <button onClick={() => setHistoryType(historyType === 'category' ? null : 'category')}>과거 분류 기록 {historyType === 'category' ? '닫기' : '보기'}</button>}{canAnalyze && <button className="reanalyze-button" disabled={analyzing} onClick={onAnalyze}>{analyzing ? '재분석 중...' : '현재 텍스트로 재분석'}</button>}</div>
    {historyType && <AnalysisHistory analyses={(grouped[historyType] ?? []).slice(1)} type={historyType} textVersion={document.text_version}/>}
  </div>
}

function AnalysisCard({ analysis, textVersion, compact = false }) {
  const contentRef = useRef(null)
  const [expanded, setExpanded] = useState(false)
  const [expandable, setExpandable] = useState(false)
  const collapsed = !compact && !expanded
  useEffect(() => {
    if (compact || expanded || !contentRef.current) return undefined
    const measure = () => {
      const content = contentRef.current
      setExpandable(Boolean(content && content.scrollHeight > content.clientHeight + 1))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [analysis, compact, expanded])
  return <article className={`detail-card${compact ? ' compact-analysis' : ''}`}>
    <header><h2>{analysis.analyzer_type === 'summary' ? '문서 요약' : '문서 분류'}</h2>{analysis.source_text_revision !== textVersion && <span className="stale-badge">이전 텍스트 기준</span>}</header>
    <AnalysisBody analysis={analysis} collapsed={collapsed} contentRef={contentRef}/>
    {expandable && <button type="button" className="analysis-expand" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? '간략히 보기' : '전체 내용 보기'}</button>}
    <AnalysisScope result={analysis.result ?? {}}/>
    <footer>{analysis.model_name} · {analysis.prompt_version ?? "이전 프롬프트"} · 텍스트 v{analysis.source_text_revision} · {new Date(analysis.created_at).toLocaleString()}</footer>
  </article>
}
function AnalysisHistory({ analyses, type, textVersion }) { return <section className="analysis-history"><h3>과거 {type === 'summary' ? '요약' : '분류'} 기록</h3>{analyses.length ? analyses.map(item => <AnalysisCard key={item.id} analysis={item} textVersion={textVersion} compact/>) : <p>과거 기록이 없습니다.</p>}</section> }
function AnalysisBody({ analysis, collapsed = false, contentRef }) {
  const result = analysis.result ?? {}
  if (analysis.analyzer_type === 'summary') return <p ref={contentRef} className={`analysis-copy${collapsed ? ' is-collapsed' : ''}`}>{result.summary ?? '요약 내용이 없습니다.'}</p>
  if (analysis.analyzer_type === 'category') return <dl className="category-result"><dt>주 분류</dt><dd>{getAnalysisCategoryLabel(result.category)}</dd>{result.traits?.length > 0 && <><dt>함께 포함된 성격</dt><dd>{result.traits.map(value => TRAIT_LABELS[value] ?? value).join(' · ')}</dd></>}<dt>근거</dt><dd ref={contentRef} className={collapsed ? 'analysis-reason is-collapsed' : 'analysis-reason'}>{result.reason ?? '-'}</dd></dl>
  return <pre>{JSON.stringify(result, null, 2)}</pre>
}
function groupAnalyses(analyses) { return analyses.reduce((result, item) => { (result[item.analyzer_type] ??= []).push(item); result[item.analyzer_type].sort((a, b) => new Date(b.created_at) - new Date(a.created_at) || b.id - a.id); return result }, {}) }

function AnalysisScope({ result }) {
  return <>
    {result.input_scope?.truncated && <p role="note">분류는 원문 중 앞·중간·뒤 일부를 참고했습니다. {result.input_scope.included_chars?.toLocaleString()} / {result.input_scope.original_chars?.toLocaleString()}자</p>}
    {result.strategy === 'hierarchical' && <p role="note">원문 전체 {result.chunk_count}개 구간을 처리한 뒤 선택한 근거로 요약했습니다. {result.call_count}회 호출{result.hard_split_count > 0 ? ` · ${result.hard_split_count}개 구간은 크기 제한으로 문장·표 중간에서 나뉘었습니다.` : ''}{result.empty_evidence_chunks?.length > 0 ? ` · ${result.empty_evidence_chunks.length}개 구간에서는 핵심 근거가 선택되지 않았습니다.` : ''}</p>}
    {result.evidence?.length > 0 && <details><summary>요약 근거 원문 확인</summary><p>인용의 원문 존재를 검사했습니다. 요약 의미의 정확성은 원문과 함께 확인해 주세요.</p>{result.evidence.filter(item => result.evidence_ids?.includes(item.id)).map(item => <blockquote key={item.id}><p>{item.quote}</p><small>원문 {item.start + 1}~{item.end}자 · 상태: {item.status}</small></blockquote>)}</details>}
  </>
}
