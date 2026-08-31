// AI 8분류. 사용자 지정 document_type(기존 BILLING 포함)과 별도로 표시한다.
export const ANALYSIS_CATEGORY_LABELS = {
  RFP: '제안요청서·입찰공고',
  PROPOSAL: '제안서·기술제안서',
  COST_SHEET: '산출내역서·견적서·원가계산서',
  CONTRACT: '계약서·과업지시서·착수신고서',
  CONTRACT_CHANGE: '변경계약서·과업변경합의서',
  REPORT: '보고서·검사조서',
  MEETING_NOTES: '회의록',
  ETC: '대가지급청구서·세금계산서·그 외',
}

export function getAnalysisCategoryLabel(value) {
  // 과거 한국어 6분류 결과를 새 분류로 임의 변환하지 않는다.
  return ANALYSIS_CATEGORY_LABELS[value] ?? value ?? '-'
}
