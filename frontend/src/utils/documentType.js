// =============================================================================
// 이 파일의 책임: 문서 유형(documents.document_type) 값을 화면 문구로 바꾼다.
//   업로드 모달과 대시보드 유형 분포가 같은 표기를 쓰게 하는 것이 목적이다.
// 다른 파일과의 관계: features/documents/DocumentUploadModal.jsx 의 선택 목록과
//   features/dashboard/DashboardView.jsx 의 유형 분포가 이 목록을 쓴다.
//   utils/documentStatus.js 와 같은 자리다 — 상태값 표기를 한 곳에 모아 화면마다
//   다르게 보이는 일을 막는 파일.
// Spring 비교: 코드값 → 표시명 매핑을 담은 공용 CodeTable 이나 MessageSource 에
//   해당한다. 상태를 갖지 않는 순수 함수만 둔다.
//
// 이 파일을 따로 만든 이유
//   전에는 이 목록이 DocumentUploadModal.jsx 안에만 있었다. 대시보드가 유형
//   분포를 보여주려고 목록을 복사하면, 나중에 한쪽 문구만 고쳐서 업로드 화면과
//   대시보드가 같은 유형을 다르게 부르게 된다. 에러가 나지 않아 알아채기 어렵다.
//   백엔드 값 목록은 models/enums.py 의 DocumentType 9종이다.
// =============================================================================

// [값, 표시명]. 순서는 업로드 모달의 선택 순서이기도 하다 — 문서가 만들어지는
// 흐름(제안요청서 → 제안서 → 산출내역서 → 계약서 → ...)에 맞춰 둔 것이다.
export const DOCUMENT_TYPES = [
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

const LABELS = Object.fromEntries(DOCUMENT_TYPES)

/** 문서 유형 값을 표시명으로. null·빈 값은 "미분류" 다.
 *
 * document_type 은 nullable 이다. 업로드할 때 유형을 고르지 않으면 비어 있고
 * AI 분류가 채우기 전까지 그대로다. "미분류" 는 유형 이름이 아니라 유형이 없는
 * 상태를 가리킨다 — ETC(기타)와 다르다. 기타는 사람이 고른 값이다.
 *
 * 목록에 없는 값이 오면 값 자체를 그대로 보여준다. 임의로 "기타" 로 바꾸면
 * 백엔드에 유형이 추가됐을 때 화면에서 그 사실이 감춰진다.
 */
export function getDocumentTypeLabel(documentType) {
  if (!documentType) return '미분류'
  return LABELS[documentType] ?? documentType
}
