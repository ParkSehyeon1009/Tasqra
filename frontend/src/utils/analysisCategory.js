// AI 7분류. 과거 COST_SHEET 결과는 ETC로 표시한다.
export const ANALYSIS_CATEGORY_LABELS = {
  RFP: '제안요청서·입찰공고',
  PROPOSAL: '제안서·기술제안서',
  CONTRACT: '계약서·과업지시서·착수신고서',
  CONTRACT_CHANGE: '변경계약서·과업변경합의서',
  REPORT: '보고서·검사조서',
  MEETING_NOTES: '회의록',
  ETC: '대가지급청구서·세금계산서·그 외',
}

export function getAnalysisCategoryLabel(value) {
  const normalized = value === 'COST_SHEET' ? 'ETC' : value
  return ANALYSIS_CATEGORY_LABELS[normalized] ?? value ?? '-'
}
