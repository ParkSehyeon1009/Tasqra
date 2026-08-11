import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getMe, logout as requestLogout } from '../api/auth'

export function useSession() {
  const queryClient = useQueryClient()
  const [token, setToken] = useState(() => localStorage.getItem('tasqra_token'))
  const meQuery = useQuery({ queryKey: ['me'], queryFn: getMe, enabled: Boolean(token), retry: false })

  useEffect(() => {
    const unauthorized = () => { setToken(null); queryClient.clear() }
    const refreshed = event => {
      setToken(event.detail.access_token)
      queryClient.setQueryData(['me'], event.detail.user)
    }
    window.addEventListener('tasqra:unauthorized', unauthorized)
    window.addEventListener('tasqra:token-refreshed', refreshed)
    return () => {
      window.removeEventListener('tasqra:unauthorized', unauthorized)
      window.removeEventListener('tasqra:token-refreshed', refreshed)
    }
  }, [queryClient])

  function login(result) {
    queryClient.clear()
    localStorage.setItem('tasqra_token', result.access_token)
    setToken(result.access_token)
    queryClient.setQueryData(['me'], result.user)
  }

  async function logout() {
    try { await requestLogout() } catch { /* 로컬 로그아웃은 항상 완료 */ }
    localStorage.removeItem('tasqra_token')
    setToken(null)
    queryClient.clear()
  }

  return { user: meQuery.data ?? null, loading: Boolean(token) && meQuery.isPending, login, logout }
}
