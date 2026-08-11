const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function parseResponse(response) {
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = data?.message || `요청 실패 (status ${response.status})`
    const error = new Error(message)
    error.code = data?.code
    error.status = response.status
    throw error
  }

  return data
}

export async function checkHealth() {
  const response = await fetch(`${API_BASE_URL}/health`)
  return parseResponse(response)
}

export async function uploadDocument(projectId, file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/documents`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${localStorage.getItem('tasqra_token')}` },
    body: formData,
  })
  return parseResponse(response)
}

export async function analyzeDocument(projectId, documentId, analyzerTypes) {
  const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/documents/${documentId}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('tasqra_token')}` },
    body: JSON.stringify({ analyzer_types: analyzerTypes ?? null }),
  })
  return parseResponse(response)
}
