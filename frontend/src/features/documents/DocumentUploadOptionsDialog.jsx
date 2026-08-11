import '../../styles/dialog.css'

export default function DocumentUploadOptionsDialog({ file, onCancel, onConfirm, uploading }) {
  if (!file) return null
  return <div className="dialog-backdrop" role="presentation">
    <section className="dialog-card upload-options" role="dialog" aria-modal="true" aria-labelledby="upload-options-title">
      <h2 id="upload-options-title">문서 처리 방식 선택</h2>
      <p><strong>{file.name}</strong>에서 가져올 내용을 선택해 주세요.</p>
      <div className="upload-option-actions">
        <button disabled={uploading} onClick={() => onConfirm('TEXT_ONLY')}><strong>문서 텍스트만 가져오기</strong><span>편집 가능한 본문과 표의 텍스트를 추출합니다.</span></button>
        <button disabled={uploading} onClick={() => onConfirm('TEXT_WITH_IMAGE_OCR')}><strong>내부 이미지도 OCR</strong><span>문서 텍스트와 삽입된 이미지의 글자를 함께 추출합니다.</span></button>
      </div>
      <button className="secondary-button" disabled={uploading} onClick={onCancel}>취소</button>
    </section>
  </div>
}
