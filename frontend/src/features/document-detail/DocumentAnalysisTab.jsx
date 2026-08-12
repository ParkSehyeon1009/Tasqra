import { useMemo, useState } from 'react'

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

function AnalysisCard({ analysis, textVersion, compact = false }) { return <article className={`detail-card${compact ? ' compact-analysis' : ''}`}><header><h2>{analysis.analyzer_type === 'summary' ? '문서 요약' : '문서 분류'}</h2>{analysis.source_text_revision !== textVersion && <span className="stale-badge">이전 텍스트 기준</span>}</header><AnalysisBody analysis={analysis}/><footer>{analysis.model_name} · 텍스트 v{analysis.source_text_revision} · {new Date(analysis.created_at).toLocaleString()}</footer></article> }
function AnalysisHistory({ analyses, type, textVersion }) { return <section className="analysis-history"><h3>과거 {type === 'summary' ? '요약' : '분류'} 기록</h3>{analyses.length ? analyses.map(item => <AnalysisCard key={item.id} analysis={item} textVersion={textVersion} compact/>) : <p>과거 기록이 없습니다.</p>}</section> }
function AnalysisBody({ analysis }) { const result = analysis.result ?? {}; if (analysis.analyzer_type === 'summary') return <p className="analysis-copy">{result.summary ?? '요약 내용이 없습니다.'}</p>; if (analysis.analyzer_type === 'category') return <dl className="category-result"><dt>분류</dt><dd>{result.category ?? '-'}</dd><dt>근거</dt><dd>{result.reason ?? '-'}</dd></dl>; return <pre>{JSON.stringify(result, null, 2)}</pre> }
function groupAnalyses(analyses) { return analyses.reduce((result, item) => { (result[item.analyzer_type] ??= []).push(item); result[item.analyzer_type].sort((a, b) => new Date(b.created_at) - new Date(a.created_at) || b.id - a.id); return result }, {}) }
