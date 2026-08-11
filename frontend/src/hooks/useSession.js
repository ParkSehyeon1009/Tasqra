import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getMe } from '../api/auth'

export function useSession() {
  const queryClient = useQueryClient()
  const [token, setToken] = useState(() => localStorage.getItem('tasqra_token'))
  const meQuery = useQuery({ queryKey: ['me'], queryFn: getMe, enabled: Boolean(token), retry: false })

  useEffect(() => {
    const unauthorized = () => { setToken(null); queryClient.removeQueries({ queryKey: ['me'] }) }
    window.addEventListener('tasqra:unauthorized', unauthorized)
    return () => window.removeEventListener('tasqra:unauthorized', unauthorized)
  }, [queryClient])

  function login(result) {
    localStorage.setItem('tasqra_token', result.access_token)
    setToken(result.access_token)
    queryClient.setQueryData(['me'], result.user)
  }

  function logout() {
    localStorage.removeItem('tasqra_token')
    setToken(null)
    queryClient.clear()
  }

  return { user: meQuery.data ?? null, loading: Boolean(token) && meQuery.isPending, login, logout }
}
