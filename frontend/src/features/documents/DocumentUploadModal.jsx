import { useEffect, useRef, useState } from 'react'
import '../../styles/dialog.css'
import './DocumentsView.css'

const DOCUMENT_TYPES = [
  ['RFP', '제안요청서·입찰공고'],
  ['PROPOSAL', '제안서·기술제안서'],
  ['COST_SHEET', '산출내역서·견적서'],
  ['CONTRACT', '계약서·과업지시서'],
  ['CONTRACT_CHANGE', '변경계약서·과업변경합의서'],
  ['REPORT', '보고서·검사조서'],
  ['MEETING_NOTES', '회의록'],
  ['BILLING', '대가지급청구서·세금계산서'],
  ['ETC', '기타'],
]

export default function DocumentUploadModal({ file, uploading, onClose, onSubmit }) {
  const [documentType, setDocumentType] = useState('')
  const [extractionStrategy, setExtractionStrategy] = useState('AUTO')
  const dialogRef = useRef(null)
  const isImage = /\.(png|jpe?g)$/i.test(file?.name ?? '')

  useEffect(() => {
    if (!file) return undefined
    function closeOnEscape(event) {
      if (event.key === 'Escape' && !uploading) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [file, onClose, uploading])

  if (!file) return null

  function submit(event) {
    event.preventDefault()
    onSubmit(file, extractionStrategy, documentType || null)
  }

  return <div className='dialog-backdrop' onMouseDown={event => { if (event.target === event.currentTarget && !uploading) onClose() }}>
    <form className='project-dialog document-upload-dialog' ref={dialogRef} onSubmit={submit} role='dialog' aria-modal='true' aria-labelledby='document-upload-title'>
      <header><div><p className='eyebrow'>DOCUMENT UPLOAD</p><h2 id='document-upload-title'>문서 업로드</h2></div><button type='button' className='dialog-close' onClick={onClose} disabled={uploading} aria-label='문서 업로드 창 닫기'>×</button></header>
      <div className='upload-file-summary'><span className='file-icon' aria-hidden='true'>{file.name.split('.').pop()?.toUpperCase()}</span><div><strong>{file.name}</strong><small>{formatFileSize(file.size)}</small></div></div>
      <label>문서 유형 <small>선택하지 않으면 자동 분류</small><select autoFocus value={documentType} onChange={event => setDocumentType(event.target.value)} disabled={uploading}><option value=''>자동 분류</option>{DOCUMENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>텍스트 추출 방식<select value={extractionStrategy} onChange={event => setExtractionStrategy(event.target.value)} disabled={uploading || isImage}><option value='AUTO'>자동 선택</option><option value='TEXT_ONLY'>문서 텍스트만</option><option value='TEXT_WITH_IMAGE_OCR'>문서 텍스트 + 이미지 OCR</option></select>{isImage && <small>이미지 파일은 OCR 방식으로 자동 처리됩니다.</small>}</label>
      <footer><button type='button' onClick={onClose} disabled={uploading}>취소</button><button type='submit' className='primary' disabled={uploading}>{uploading ? '업로드 중…' : '업로드'}</button></footer>
    </form>
  </div>
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
