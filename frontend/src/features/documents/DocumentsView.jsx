import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeading from '../../components/common/PageHeading'
import { getDocumentCharacterCounts, getDocumentPrimaryAction, getDocumentStatus, getReviewStatus } from '../../utils/documentStatus'
import { formatNumber } from '../../utils/format'
import './DocumentsView.css'
import './DocumentReviewBadge.css'

export default function DocumentsView({ projectId, documents, canEdit, onUpload, onFileDrop, uploading, uploadingFileName }) {
  const [dragging, setDragging] = useState(false)
  const navigate = useNavigate()
  const openDocument = documentId => navigate('/projects/' + projectId + '/documents/' + documentId)
  const openPrimaryAction = document => {
    if (['PENDING', 'IN_PROGRESS', 'COMPLETED'].includes(document.review_status)) {
      navigate('/projects/' + projectId + '/documents/' + document.id + '/review')
      return
    }
    openDocument(document.id)
  }
  const action = canEdit ? <button className='primary' disabled={uploading} onClick={onUpload}>문서 업로드</button> : null

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

  return <><PageHeading eyebrow='PROJECT DOCUMENTS' title='문서' description='문서의 처리와 OCR 검수 상태를 확인하고 다음 작업을 이어가세요.' action={action}/>
    <section className={'panel table-panel document-drop-target' + (dragging ? ' is-dragging' : '')} onDragEnter={handleDragOver} onDragOver={handleDragOver} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }} onDrop={handleDrop}>
      {dragging && <div className='drop-overlay'>여기에 파일을 놓아 업로드하세요.</div>}
      <div className='panel-head'><div><h2>전체 문서</h2><p>상태 배지와 설명은 현재 서버가 제공한 값에 따라 표시됩니다.</p></div><span>{documents.length}건</span></div>
      {uploading && <ProcessingDocument filename={uploadingFileName}/>}
      {documents.length ? <DocumentList documents={documents} onOpen={openDocument} onPrimaryAction={openPrimaryAction}/> : !uploading && <EmptyDocuments onUpload={onUpload} canEdit={canEdit}/>}
      {canEdit && documents.length > 0 && <UploadDropHint onUpload={onUpload}/>}
    </section>
  </>
}

function DocumentList({ documents, onOpen, onPrimaryAction }) {
  return <ul className='document-list'>{documents.map(document => {
    const processing = ['PENDING', 'EXTRACTING', 'ANALYZING'].includes(document.status)
    const documentStatus = getDocumentStatus(document.status)
    const reviewStatus = getReviewStatus(document.review_status)
    return <li className='document-row' key={document.id}>
      <button className='document-main-action' onClick={() => onOpen(document.id)} aria-label={document.filename + ' 상세 보기'}>
        <span className='file-icon' aria-hidden='true'>{document.file_type?.toUpperCase()}</span>
        <span className='document-primary-copy'><strong>{document.filename}</strong><DocumentCharacterCounts document={document}/></span>
      </button>
      <div className='document-state-stack'>
        <StatusBadge label={documentStatus.label} description={documentStatus.description} tone={documentStatus.tone}/>
        <StatusBadge label={reviewStatus.label} description={reviewStatus.description} tone={reviewStatus.tone}/>
      </div>
      <div className='document-secondary-meta'><span className='type-pill'>{document.document_type || '미분류'}</span><time dateTime={document.created_at}>{new Date(document.created_at).toLocaleDateString()}</time></div>
      <div className='document-actions'>
        {document.review_status === 'COMPLETED' ? <><button className='document-open' onClick={() => onPrimaryAction(document)}>재검수하기</button><button className='document-open' onClick={() => onOpen(document.id)}>상세보기</button></> : <button className='document-open' onClick={() => onPrimaryAction(document)}>{getDocumentPrimaryAction(document)}</button>}
      </div>
      {(processing || document.status === 'FAILED') && <p className='document-state-note' role='status'>{document.processing_error || documentStatus.description}</p>}
    </li>
  })}</ul>
}

function StatusBadge({ label, description, tone }) {
  return <span className={'status-badge status-' + tone} title={description}><span aria-hidden='true' className='status-badge-dot'/>{label}</span>
}

function DocumentCharacterCounts({ document }) {
  const counts = getDocumentCharacterCounts(document)
  return <small className='document-character-counts'>{counts.length ? counts.map(item => <span key={item.label}>{item.label} {formatNumber(item.value)}자</span>) : '문자 수 정보 없음'}</small>
}

function ProcessingDocument({ filename }) {
  return <div className='processing-document' role='status'><span className='processing-spinner'/><div><strong>{filename ?? '문서'} 업로드 중</strong><p>파일을 서버에 전송하고 있습니다. 완료되면 실제 처리 상태가 표시됩니다.</p></div></div>
}

function EmptyDocuments({ onUpload, canEdit }) {
  return <div className='drop-zone'><b aria-hidden='true'>↑</b><h2>아직 등록된 문서가 없습니다.</h2><p>PDF, DOCX, HWPX, JPG 또는 PNG 파일을 업로드하면 처리와 검수 상태를 이곳에서 확인할 수 있습니다.</p>{canEdit && <button onClick={onUpload}>파일 선택</button>}</div>
}

function UploadDropHint({ onUpload }) {
  return <div className='upload-drop-hint'><span>추가 문서가 있나요?</span><button onClick={onUpload}>파일 업로드</button></div>
}
