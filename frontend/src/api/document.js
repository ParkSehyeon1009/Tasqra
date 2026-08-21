import { http } from './http'

// GET /api/documents — 목록 + 검색 + 페이징
// 응답: { items, page, size, total, total_pages }
export async function listDocuments(projectId, { q, documentType, category, page = 1, size = 20 } = {}) {
  const params = { page, size }
  if (q) params.q = q
  if (documentType) params.document_type = documentType
  if (category) params.category = category

  const { data } = await http.get(`/api/projects/${projectId}/documents`, { params })
  return data
}

// GET /api/documents/{id} — 상세 (원문 + 분석 결과 포함)
export async function getDocument(projectId, documentId) {
  const { data } = await http.get(`/api/projects/${projectId}/documents/${documentId}`)
  return data
}

export async function getDocumentHistory(projectId, documentId) {
  return (await http.get(`/api/projects/${projectId}/documents/${documentId}/history`)).data
}

export async function downloadDocumentSource(projectId, documentId, filename) {
  const response = await http.get(`/api/projects/${projectId}/documents/${documentId}/source`, { responseType: 'blob' })
  triggerBrowserDownload(response.data, filename)
}

export async function getOcrReview(projectId, documentId) {
  return (await http.get(`/api/projects/${projectId}/documents/${documentId}/review`)).data
}

export async function getOcrPageImage(imageUrl) {
  const response = await http.get(imageUrl, { responseType: 'blob' })
  return await blobToDataUrl(response.data)
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

export async function updateOcrElement(projectId, documentId, elementId, text, version) {
  return (await http.patch(`/api/projects/${projectId}/documents/${documentId}/ocr-elements/${elementId}`, { text, version })).data
}

export async function updateOcrElementsBatch(projectId, documentId, items) {
  return (await http.patch(`/api/projects/${projectId}/documents/${documentId}/ocr-elements`, { items })).data
}

export async function setOcrElementExclusion(projectId, documentId, elementId, isExcluded, version) {
  return (await http.patch(`/api/projects/${projectId}/documents/${documentId}/ocr-elements/${elementId}/exclusion`, { is_excluded: isExcluded, version })).data
}

export async function createOcrElement(projectId, documentId, element) {
  return (await http.post(`/api/projects/${projectId}/documents/${documentId}/ocr-elements`, element)).data
}

export async function setOcrElementDeletion(projectId, documentId, elementId, isDeleted, version) {
  return (await http.patch(`/api/projects/${projectId}/documents/${documentId}/ocr-elements/${elementId}/deletion`, { is_deleted: isDeleted, version })).data
}

export async function reprocessOcrElement(projectId, documentId, element) {
  const { x, y, width, height } = element
  return (await http.post(`/api/projects/${projectId}/documents/${documentId}/ocr-elements/${element.id}/reprocess`, { x, y, width, height })).data
}

export async function mergeOcrElements(projectId, documentId, elements) {
  return (await http.post(`/api/projects/${projectId}/documents/${documentId}/ocr-elements/merge`, { items: elements.map(element => ({ id: element.id, version: element.version })) })).data
}

export async function completeOcrReview(projectId, documentId) {
  return (await http.post(`/api/projects/${projectId}/documents/${documentId}/review/complete`)).data
}

// GET /api/documents/{id}/download?format=txt — 요약 .txt 다운로드
// 서버가 Content-Disposition 에 한글 파일명을 UTF-8 로 인코딩해 보내므로,
// 그 값을 파싱해 실제 파일명으로 저장한다.
export async function downloadSummary(projectId, documentId, fallbackName = 'summary.txt') {
  const response = await http.get(`/api/projects/${projectId}/documents/${documentId}/download`, {
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
export async function analyzeDocument(projectId, documentId, analyzerTypes = null) {
  const body = analyzerTypes ? { analyzer_types: analyzerTypes } : {}
  const { data } = await http.post(`/api/projects/${projectId}/documents/${documentId}/analyze`, body)
  return data
}

// DELETE /api/documents/{id} — 문서·추출 텍스트·분석 결과·원본 파일 삭제
// 성공 시 본문이 없으므로(204) 반환값이 없다.
export async function deleteDocument(projectId, documentId) {
  await http.delete(`/api/projects/${projectId}/documents/${documentId}`)
}

export async function retryDocumentProcessing(projectId, documentId) {
  return (await http.post(`/api/projects/${projectId}/documents/${documentId}/retry`)).data
}
