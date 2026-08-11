import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const http = axios.create({ baseURL: API_BASE_URL, timeout: 120000, withCredentials: true })
let refreshPromise = null

http.interceptors.request.use(config => {
  const token = localStorage.getItem('tasqra_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
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
    normalized.requestId = data?.request_id
    if (normalized.status === 401) {
      localStorage.removeItem('tasqra_token')
      window.dispatchEvent(new Event('tasqra:unauthorized'))
    }
    return Promise.reject(normalized)
  },
)
