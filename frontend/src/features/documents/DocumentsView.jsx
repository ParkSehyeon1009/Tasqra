import { useState } from 'react'
import PageHeading from '../../components/common/PageHeading'
import './DocumentsView.css'

export default function DocumentsView({ documents, canEdit, onUpload, onFileDrop, uploading }) {
  const [dragging, setDragging] = useState(false)
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
      {documents.length ? <DocumentList documents={documents}/> : <EmptyDocuments onUpload={onUpload} canEdit={canEdit}/>}</section></>
}

function DocumentList({ documents }) {
  return <ul className="document-list">{documents.map(document => <li key={document.id}><span className="file-icon">{document.file_type?.toUpperCase()}</span><div><strong>{document.filename}</strong><small>{document.extract_method || '처리 완료'} · {document.char_count?.toLocaleString() || 0}자</small></div><span className="type-pill">{document.document_type || '미분류'}</span><span className="complete-pill">{document.status}</span><time>{new Date(document.created_at).toLocaleDateString()}</time></li>)}</ul>
}

function EmptyDocuments({ onUpload, canEdit }) {
  return <div className="drop-zone"><b>↑</b><h2>파일을 끌어놓거나 선택해 업로드하세요.</h2><p>PDF · DOCX · HWPX · JPG · PNG</p>{canEdit && <button onClick={onUpload}>파일 선택</button>}</div>
}
