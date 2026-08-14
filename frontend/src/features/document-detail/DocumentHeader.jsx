import { getDocumentCharacterCounts, getDocumentStatus, getReviewStatus } from '../../utils/documentStatus'
import { formatNumber } from '../../utils/format'

export default function DocumentHeader({ document, onBack, onDownload, onRetry, onDelete, canEdit, busy }) {
  const documentStatus = getDocumentStatus(document.status)
  const reviewStatus = getReviewStatus(document.review_status)
  const counts = getDocumentCharacterCounts(document)
  return <header className='document-page-header'>
    <div><button className='back-button' onClick={onBack}>← 문서 목록</button><div className='document-title-line'><span className='detail-file-icon'>{document.file_type.toUpperCase()}</span><div><h1>{document.filename}</h1><p>{document.file_type.toUpperCase()} · 총 {document.page_count ?? 0}쪽{counts.length ? ' · ' : ''}{counts.map(item => item.label + ' ' + formatNumber(item.value) + '자').join(' · ')}</p>{document.processing_error && <p className='document-processing-error'>{document.processing_error}</p>}</div></div></div>
    <div className='document-page-actions'><div className='document-header-statuses'><StatusPill status={documentStatus}/><StatusPill status={reviewStatus}/></div>{document.status === 'FAILED' && canEdit && <button className='retry-processing' onClick={onRetry} disabled={busy}>다시 처리</button>}<button onClick={onDownload} disabled={busy}>원본 다운로드</button>{canEdit && <button className='danger-outline' onClick={onDelete} disabled={busy}>문서 삭제</button>}</div>
  </header>
}

function StatusPill({ status }) {
  return <span className={'status-badge status-' + status.tone} title={status.description}><span aria-hidden='true' className='status-badge-dot'/>{status.label}</span>
}
