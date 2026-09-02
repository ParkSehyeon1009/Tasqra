// 화면마다 동일한 API 상태값을 같은 문구·설명·색상으로 표시하기 위한 순수 함수입니다.
// 백엔드 상태값이나 API 계약을 변경하지 않습니다.
const documentStatuses = {
  PENDING: { label: '업로드 대기', description: '업로드가 접수되어 처리를 기다리고 있습니다.', tone: 'neutral' },
  EXTRACTING: { label: '텍스트 추출 중', description: '문서에서 읽을 수 있는 텍스트를 추출하고 있습니다.', tone: 'progress' },
  EXTRACTED: { label: '추출 완료', description: '텍스트 추출이 완료되었습니다. 검수 상태를 확인해 주세요.', tone: 'ready' },
  ANALYZING: { label: '분석 중', description: '추출된 텍스트를 분석하고 있습니다.', tone: 'progress' },
  COMPLETED: { label: '추출 완료', description: '텍스트 추출이 완료되었습니다. 검수 상태를 확인해 주세요.', tone: 'success' },
  FAILED: { label: '처리 실패', description: '처리 중 오류가 발생했습니다. 문서 상세에서 안내를 확인해 주세요.', tone: 'danger' },
}

const reviewStatuses = {
  NOT_REQUIRED: { label: 'OCR 검수 대상 없음', description: 'OCR 검수 없이 추출이 완료된 문서입니다.', tone: 'neutral' },
  PENDING: { label: 'OCR 검수 필요', description: 'OCR로 인식한 내용을 확인하고 확정해 주세요.', tone: 'attention' },
  IN_PROGRESS: { label: 'OCR 검수 진행 중', description: '저장한 수정 내용이 최종 텍스트에 반영되기 전입니다.', tone: 'attention' },
  COMPLETED: { label: 'OCR 검수 완료', description: '검수한 내용이 최종 텍스트에 반영되었습니다.', tone: 'success' },
}

export function getDocumentStatus(status) {
  return documentStatuses[status] ?? { label: status || '상태 확인 중', description: '현재 문서 상태를 확인하고 있습니다.', tone: 'neutral' }
}

export function getReviewStatus(status) {
  return reviewStatuses[status] ?? { label: status || '검수 상태 확인 중', description: '현재 OCR 검수 상태를 확인하고 있습니다.', tone: 'neutral' }
}

export function getDocumentPrimaryAction(document) {
  if (document?.status === 'FAILED') return '문서 상세에서 오류 확인'
  if (['PENDING', 'EXTRACTING', 'ANALYZING'].includes(document?.status)) return '처리 상태 확인'
  if (['PENDING', 'IN_PROGRESS'].includes(document?.review_status)) return 'OCR 검수하기'
  if (document?.review_status === 'COMPLETED') return '재검수하기'
  return '상세보기'
}

export function getDocumentCharacterCounts(document) {
  const items = []
  if (document?.text_char_count !== null && document?.text_char_count !== undefined) items.push({ label: '텍스트', value: document.text_char_count })
  if (document?.ocr_char_count !== null && document?.ocr_char_count !== undefined && document.ocr_char_count > 0) items.push({ label: 'OCR', value: document.ocr_char_count })
  if (!items.length && document?.char_count !== null && document?.char_count !== undefined) items.push({ label: '문자 수', value: document.char_count })
  return items
}
