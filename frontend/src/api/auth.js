import { http } from './http'

export async function signup(payload) {
  const { data } = await http.post('/api/auth/signup', payload)
  return data
}
export async function login(payload) {
  const { data } = await http.post('/api/auth/login', payload)
  return data
}
export async function getMe() {
  const { data } = await http.get('/api/auth/me')
  return data
}
export async function logout() { await http.post('/api/auth/logout') }
