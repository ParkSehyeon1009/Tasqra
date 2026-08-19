import { useEffect, useRef, useState } from 'react'
import '../../styles/dialog.css'
import './DocumentsView.css'
// 목록을 utils/documentType.js 로 옮겼다. 대시보드 유형 분포도 같은 표기를
// 써야 해서다 — 복사해 두면 한쪽만 고쳐져 같은 유형이 다르게 불린다.
import { DOCUMENT_TYPES } from '../../utils/documentType'
import { isImageUpload, validateUploadFiles } from '../document-upload/uploadValidation'

export default function DocumentUploadModal({ files, uploading, onClose, onRemove, onSubmit }) {
  const [documentType, setDocumentType] = useState('')
  const [extractionStrategy, setExtractionStrategy] = useState('AUTO')
  const dialogRef = useRef(null)
  const validatedFiles = validateUploadFiles(files)
  const validFiles = validatedFiles.filter(item => !item.error).map(item => item.file)
  const allImages = validFiles.length > 0 && validFiles.every(isImageUpload)

  useEffect(() => {
    if (!files?.length) return undefined
    function closeOnEscape(event) {
      if (event.key === 'Escape' && !uploading) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [files, onClose, uploading])

  if (!files?.length) return null

  function submit(event) {
    event.preventDefault()
    if (!validFiles.length) return
    onSubmit(validFiles, extractionStrategy, documentType || null)
  }

  return <div className='dialog-backdrop' onMouseDown={event => { if (event.target === event.currentTarget && !uploading) onClose() }}>
    <form className='project-dialog document-upload-dialog' ref={dialogRef} onSubmit={submit} role='dialog' aria-modal='true' aria-labelledby='document-upload-title'>
      <header><div><p className='eyebrow'>DOCUMENT UPLOAD</p><h2 id='document-upload-title'>문서 업로드</h2></div><button type='button' className='dialog-close' onClick={onClose} disabled={uploading} aria-label='문서 업로드 창 닫기'>×</button></header>
      <div className='upload-file-list' aria-label={`선택한 파일 ${files.length}개`}>{validatedFiles.map(({ file, key, index, error }) => <div className={'upload-file-summary' + (error ? ' is-invalid' : '')} key={key}><span className='file-icon' aria-hidden='true'>{file.name.split('.').pop()?.toUpperCase()}</span><div><strong>{file.name}</strong><small>{formatFileSize(file.size)}{error ? ` · ${error}` : ''}</small></div><button type='button' onClick={() => onRemove(index)} disabled={uploading} aria-label={`${file.name} 선택 해제`}>제거</button></div>)}</div>
      <label>문서 유형 <small>선택하지 않으면 자동 분류</small><select autoFocus value={documentType} onChange={event => setDocumentType(event.target.value)} disabled={uploading}><option value=''>자동 분류</option>{DOCUMENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <label>텍스트 추출 방식<select value={extractionStrategy} onChange={event => setExtractionStrategy(event.target.value)} disabled={uploading || allImages}><option value='AUTO'>자동 선택</option><option value='TEXT_ONLY'>문서 텍스트만</option><option value='TEXT_WITH_IMAGE_OCR'>문서 텍스트 + 이미지 OCR</option></select>{allImages && <small>이미지 파일은 OCR 방식으로 자동 처리됩니다.</small>}{!allImages && validFiles.some(isImageUpload) && <small>이미지 파일에는 선택과 관계없이 OCR 방식이 적용됩니다.</small>}</label>
      <footer><button type='button' onClick={onClose} disabled={uploading}>취소</button><button type='submit' className='primary' disabled={uploading || !validFiles.length}>{uploading ? '업로드 중…' : `${validFiles.length}개 업로드`}</button></footer>
    </form>
  </div>
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
