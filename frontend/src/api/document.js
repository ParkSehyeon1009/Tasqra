import { http } from './http'

// GET /api/documents — 목록 + 검색 + 페이징
// 응답: { items, page, size, total, total_pages }
export async function listDocuments({ q, documentType, category, page = 1, size = 20 } = {}) {
  const params = { page, size }
  if (q) params.q = q
  if (documentType) params.document_type = documentType
  if (category) params.category = category

  const { data } = await http.get('/api/documents', { params })
  return data
}

// GET /api/documents/{id} — 상세 (원문 + 분석 결과 포함)
export async function getDocument(documentId) {
  const { data } = await http.get(`/api/documents/${documentId}`)
  return data
}

// GET /api/documents/{id}/download?format=txt — 요약 .txt 다운로드
// 서버가 Content-Disposition 에 한글 파일명을 UTF-8 로 인코딩해 보내므로,
// 그 값을 파싱해 실제 파일명으로 저장한다.
export async function downloadSummary(documentId, fallbackName = 'summary.txt') {
  const response = await http.get(`/api/documents/${documentId}/download`, {
    params: { format: 'txt' },
    responseType: 'blob',
  })

  const filename = parseFilename(response.headers['content-disposition'], fallbackName)
  triggerBrowserDownload(response.data, filename)
  return filename
}

// Content-Disposition: attachment; filename="summary.txt"; filename*=UTF-8''%ED%95%9C...
function parseFilename(disposition, fallback) {
  if (!disposition) return fallback

  // filename*=UTF-8'' 형식을 우선 사용한다 (한글 파일명).
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      // 디코딩 실패 시 아래 filename= 으로 넘어간다
    }
  }

  const asciiMatch = disposition.match(/filename="?([^";]+)"?/i)
  return asciiMatch ? asciiMatch[1] : fallback
}

// blob 을 사용자 다운로드로 연결한다. (a 태그를 임시로 만들어 클릭)
function triggerBrowserDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

// POST /api/documents/{id}/analyze — AI 요약 + 카테고리 분류 실행
// analyzerTypes 를 생략하면 서버가 summary/category 둘 다 실행한다.
// AnalyzeRequest 는 body 가 필수라서, 생략 시에도 빈 객체를 보내야 422 가 나지 않는다.
export async function analyzeDocument(documentId, analyzerTypes = null) {
  const body = analyzerTypes ? { analyzer_types: analyzerTypes } : {}
  const { data } = await http.post(`/api/documents/${documentId}/analyze`, body)
  return data
}

// DELETE /api/documents/{id} — 문서·추출 텍스트·분석 결과·원본 파일 삭제
// 성공 시 본문이 없으므로(204) 반환값이 없다.
export async function deleteDocument(documentId) {
  await http.delete(`/api/documents/${documentId}`)
}
