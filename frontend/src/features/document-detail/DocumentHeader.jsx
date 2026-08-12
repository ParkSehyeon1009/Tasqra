export default function DocumentHeader({ document, onBack, onDownload, onDelete, canEdit, busy }) {
  return <header className="document-page-header">
    <div><button className="back-button" onClick={onBack}>← 문서 목록</button><div className="document-title-line"><span className="detail-file-icon">{document.file_type.toUpperCase()}</span><div><h1>{document.filename}</h1><p>{document.file_type.toUpperCase()} · {document.page_count ?? 0}페이지 · {document.char_count?.toLocaleString() ?? 0}자</p></div></div></div>
    <div className="document-page-actions"><StatusPill label={statusLabel(document.status)} tone="blue"/><StatusPill label={reviewLabel(document.review_status)} tone={document.review_status === 'COMPLETED' ? 'green' : 'amber'}/><button onClick={onDownload} disabled={busy}>원본 다운로드</button>{canEdit && <button className="danger-outline" onClick={onDelete} disabled={busy}>문서 삭제</button>}</div>
  </header>
}

function StatusPill({ label, tone }) { return <span className={`detail-status detail-status-${tone}`}>{label}</span> }
function statusLabel(status) { return { PENDING: '대기 중', EXTRACTING: '추출 중', EXTRACTED: '추출 완료', ANALYZING: '분석 중', COMPLETED: '처리 완료', FAILED: '처리 실패' }[status] ?? status }
function reviewLabel(status) { return { NOT_REQUIRED: '검수 불필요', PENDING: '검수 필요', IN_PROGRESS: '검수 중', COMPLETED: '검수 완료' }[status] ?? status }
