import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeading from '../../components/common/PageHeading'
import './DocumentsView.css'
import './DocumentReviewBadge.css'

export default function DocumentsView({ projectId, documents, canEdit, onUpload, onFileDrop, uploading, uploadingFileName }) {
  const [dragging, setDragging] = useState(false)
  const navigate = useNavigate()
  const openDocument = documentId => navigate(`/projects/${projectId}/documents/${documentId}`)
  const action = canEdit ? <button className="primary" disabled={uploading} onClick={onUpload}>문서 업로드</button> : null
  function handleDragOver(event) {
    if (!canEdit) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    setDragging(true)
  }
  function handleDrop(event) {
    if (!canEdit) return
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file) onFileDrop(file)?.catch?.(() => {})
  }
  return <><PageHeading eyebrow="PROJECT DOCUMENTS" title="문서" description="업로드된 문서와 처리 상태를 확인합니다." action={action}/>
    <section className={`panel table-panel document-drop-target${dragging ? ' is-dragging' : ''}`} onDragEnter={handleDragOver} onDragOver={handleDragOver} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }} onDrop={handleDrop}>
      {dragging && <div className="drop-overlay">여기에 파일을 놓아 업로드하세요.</div>}
      <div className="panel-head"><h2>전체 문서</h2><span>{documents.length}건</span></div>
      {uploading && <ProcessingDocument filename={uploadingFileName}/>}
      {documents.length ? <DocumentList documents={documents} onSelect={openDocument}/> : !uploading && <EmptyDocuments onUpload={onUpload} canEdit={canEdit}/>}
      {canEdit && documents.length > 0 && <UploadDropHint onUpload={onUpload}/>}
    </section>
  </>
}

function DocumentList({ documents, onSelect }) {
  return <ul className="document-list">{documents.map(document => <li className="document-row" key={document.id} onClick={() => onSelect(document.id)}><span className="file-icon">{document.file_type?.toUpperCase()}</span><div><strong>{document.filename}</strong><DocumentCharacterCounts document={document}/></div><span className="type-pill">{document.document_type || '미분류'}</span><ReviewBadge status={document.review_status}/><span className={`complete-pill status-${document.status?.toLowerCase()}`}>{statusLabel(document.status)}</span><time>{new Date(document.created_at).toLocaleDateString()}</time><button className="document-open" onClick={event => { event.stopPropagation(); onSelect(document.id) }}>내용 보기</button></li>)}</ul>
}

function DocumentCharacterCounts({ document }) {
  const textCount = document.text_char_count ?? document.char_count ?? 0
  const ocrCount = document.ocr_char_count ?? 0
  const counts = [
    textCount > 0 && `TEXT ${textCount.toLocaleString()}자`,
    ocrCount > 0 && `OCR ${ocrCount.toLocaleString()}자`,
  ].filter(Boolean)
  return <small>{counts.join(' · ') || '처리 대기'}</small>
}

function ProcessingDocument({ filename }) {
  return <div className="processing-document" role="status"><span className="processing-spinner"/><div><strong>{filename ?? '문서'} 처리 중</strong><p>파일을 읽고 텍스트를 추출하고 있습니다. 완료될 때까지 잠시 기다려 주세요.</p></div></div>
}

function UploadDropHint({ onUpload }) {
  return <button className="upload-drop-hint" onClick={onUpload}><span>＋</span><div><strong>문서 추가 업로드</strong><small>이 영역에 파일을 끌어놓거나 클릭해서 선택하세요.</small></div></button>
}

function EmptyDocuments({ onUpload, canEdit }) {
  return <div className="drop-zone"><b>↑</b><h2>파일을 끌어놓거나 선택해 업로드하세요.</h2><p>PDF · DOCX · HWPX · JPG · PNG</p>{canEdit && <button onClick={onUpload}>파일 선택</button>}</div>
}

function statusLabel(status) {
  return { PENDING: '대기 중', EXTRACTING: '추출 중', EXTRACTED: '추출 완료', ANALYZING: '분석 중', COMPLETED: '완료', FAILED: '실패' }[status] ?? status
}

function ReviewBadge({ status }) {
  if (status === 'NOT_REQUIRED') return null
  return <span className={`document-review-badge review-${status?.toLowerCase()}`}>{({ PENDING: '검수 필요', IN_PROGRESS: '검수 중', COMPLETED: '검수 완료' })[status] ?? status}</span>
}
