// =============================================================================
// 이 파일의 책임: 문서 유형의 7종 선택 목록과 레거시 값 표시 호환을 관리한다.
// 다른 파일과의 관계: 업로드·상세 수정·목록 필터·대시보드 배지가 같은 canonical
//   값과 라벨을 사용하도록 한곳에서 변환한다.
// Spring 비교: 레거시 코드 alias까지 처리하는 공용 CodeTable/Converter에 해당한다.
// =============================================================================

export const UNCLASSIFIED_DOCUMENT_TYPE = '__UNCLASSIFIED__'
export const LEGACY_BILLING_DOCUMENT_TYPE = 'BILLING'
export const LEGACY_COST_SHEET_DOCUMENT_TYPE = 'COST_SHEET'

// 사용자가 새로 선택하고 저장할 수 있는 유형은 7종이다.
export const DOCUMENT_TYPES = [
  ['RFP', '제안요청서·입찰공고'],
  ['PROPOSAL', '제안서·기술제안서'],
  ['CONTRACT', '계약서·과업지시서'],
  ['CONTRACT_CHANGE', '변경계약서·과업변경합의서'],
  ['REPORT', '보고서·검사조서'],
  ['MEETING_NOTES', '회의록'],
  ['ETC', '기타 (세금계산서·대가지급청구서 포함)'],
]

const LABELS = Object.fromEntries(DOCUMENT_TYPES)
const FILTER_VALUES = new Set([...DOCUMENT_TYPES.map(([value]) => value), UNCLASSIFIED_DOCUMENT_TYPE])

const TYPE_TONES = {
  RFP: 'rfp',
  PROPOSAL: 'proposal',
  COST_SHEET: 'cost-sheet',
  CONTRACT: 'contract',
  CONTRACT_CHANGE: 'contract-change',
  REPORT: 'report',
  MEETING_NOTES: 'meeting-notes',
  ETC: 'etc',
}

/** 배지 CSS에는 검증된 제한값만 넘긴다. */
export function getDocumentTypeTone(documentType) {
  const normalized = normalizeDocumentTypeValue(documentType)
  if (!normalized || normalized === UNCLASSIFIED_DOCUMENT_TYPE) return 'unclassified'
  return TYPE_TONES[normalized] ?? 'unclassified'
}

/** 과거 BILLING 저장값을 현재 8종 계약의 ETC로 읽는다. */
export function normalizeDocumentTypeValue(documentType) {
  return [LEGACY_BILLING_DOCUMENT_TYPE, LEGACY_COST_SHEET_DOCUMENT_TYPE].includes(documentType) ? 'ETC' : documentType
}

export function isSupportedDocumentTypeFilter(documentType) {
  return FILTER_VALUES.has(normalizeDocumentTypeValue(documentType))
}

/** 과거 BILLING URL도 ETC 필터로 복원해 신규·레거시 값을 함께 조회한다. */
export function normalizeDocumentTypeFilter(documentType) {
  const normalized = normalizeDocumentTypeValue(documentType)
  return FILTER_VALUES.has(normalized) ? normalized : ''
}

export function getDocumentTypeFilterLabel(documentType) {
  if (documentType === UNCLASSIFIED_DOCUMENT_TYPE) return '미분류'
  return getDocumentTypeLabel(documentType)
}

/** null은 미분류, 레거시 BILLING은 ETC 표시명으로 보여준다. */
export function getDocumentTypeLabel(documentType) {
  if (!documentType) return '미분류'
  const normalized = normalizeDocumentTypeValue(documentType)
  return LABELS[normalized] ?? documentType
}
