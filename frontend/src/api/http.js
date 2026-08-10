import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 분석(LLM)이 오래 걸릴 수 있어 넉넉히 둔다
})

// --- 요청 인터셉터 -----------------------------------------------------------
// 로그인 기능을 추가하면 이 자리에 토큰.
// http.interceptors.request.use((config) => {
//   const token = localStorage.getItem('token')
//   if (token) config.headers.Authorization = `Bearer ${token}`
//   return config
// })


// --- 응답 인터셉터 -----------------------------------------------------------
// 백엔드 에러 포맷을 Error 객체로 정규화한다.
// api/client.js 와 동일하게 err.code / err.message / err.status 를 제공하므로
// 두 파일을 섞어 써도 에러 처리 방식이 같다.
http.interceptors.response.use(
  (response) => response,
  async (error) => {
    let data = error.response?.data

    if (data instanceof Blob) {
      try {
        data = JSON.parse(await data.text())
      } catch {
        data = null
      }
    }

    const normalized = new Error(
      data?.message || error.message || '요청 처리 중 오류가 발생했습니다.',
    )
    normalized.code = data?.code
    normalized.status = error.response?.status
    normalized.requestId = data?.request_id
    return Promise.reject(normalized)
  },
)

