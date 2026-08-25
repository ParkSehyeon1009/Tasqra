import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const http = axios.create({ baseURL: API_BASE_URL, timeout: 120000, withCredentials: true })
let refreshPromise = null

// 요청 추적 id(SYS-003-1). 화면에서 만들어 보내면 서버가 그것을 이어받아 로그에
// 찍으므로, 응답을 받지 못한 요청(타임아웃·네트워크 끊김)도 되짚을 수 있다.
// 서버는 안전한 형태(영숫자·점·밑줄·붙임표 8~64자)만 받아들이고 어긋나면 새로
// 만든다 — core/middleware.py 의 resolve_request_id 참고.
function newRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  // randomUUID 는 보안 컨텍스트(https·localhost)에서만 있다. 없으면 대신 만든다.
  return `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

http.interceptors.request.use(config => {
  const token = localStorage.getItem('tasqra_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  config.headers['X-Request-ID'] ??= newRequestId()
  return config
})

async function refreshAccessToken() {
  const { data } = await axios.post(`${API_BASE_URL}/api/auth/refresh`, null, { withCredentials: true })
  localStorage.setItem('tasqra_token', data.access_token)
  window.dispatchEvent(new CustomEvent('tasqra:token-refreshed', { detail: data }))
  return data.access_token
}

http.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config
    const authAction = /\/api\/auth\/(login|signup|refresh|logout)$/.test(String(original?.url))
    const canRefresh = error.response?.status === 401 && !original?._retry && !authAction
    if (canRefresh) {
      original._retry = true
      try {
        refreshPromise ??= refreshAccessToken().finally(() => { refreshPromise = null })
        const token = await refreshPromise
        original.headers.Authorization = `Bearer ${token}`
        return http(original)
      } catch { /* 아래에서 세션 만료 처리 */ }
    }

    let data = error.response?.data
    if (data instanceof Blob) {
      try { data = JSON.parse(await data.text()) } catch { data = null }
    }
    const normalized = new Error(data?.message || error.message || '요청 처리 중 오류가 발생했습니다.')
    normalized.code = data?.code
    normalized.status = error.response?.status
    // 서버가 준 값이 우선이다. 응답을 못 받았거나 본문이 오류 형식이 아니면
    // 우리가 보낸 값으로 되짚는다 — 서버 로그에 같은 값이 찍혀 있다.
    normalized.requestId = data?.request_id
      ?? error.response?.headers?.['x-request-id']
      ?? original?.headers?.['X-Request-ID']
    if (normalized.status === 401) {
      localStorage.removeItem('tasqra_token')
      window.dispatchEvent(new Event('tasqra:unauthorized'))
    }
    return Promise.reject(normalized)
  },
)
