import { useState } from 'react'
import { login, signup } from '../api/auth'
import Logo from '../components/common/Logo'
import '../styles/auth.css'

const FALLBACK_ERROR = '요청 처리 중 오류가 발생했습니다.'

export default function AuthPage({ onAuthenticated, notify }) {
  const [mode, setMode] = useState('login')
  const [signupComplete, setSignupComplete] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault(); setBusy(true)
    const form = event.currentTarget
    const values = Object.fromEntries(new FormData(form))
    try {
      if (mode === 'signup') {
        await signup(values)
        form.reset(); setSignupComplete(true); setMode('login')
        notify('success', '회원가입 완료', '가입이 완료되었습니다. 아이디로 로그인해 주세요.')
        return
      }
      const result = await login(values)
      localStorage.setItem('tasqra_token', result.access_token)
      await onAuthenticated(result.user)
      notify('success', '로그인 완료', `${result.user.name}님, 환영합니다.`)
    } catch (error) { notify('error', '요청 실패', error.message || FALLBACK_ERROR) }
    finally { setBusy(false) }
  }

  function switchMode() {
    setSignupComplete(false)
    setMode(current => current === 'login' ? 'signup' : 'login')
  }

  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}>
    <Logo/><div><p className="eyebrow">DOCUMENT WORKSPACE</p><h1>{mode === 'login' ? '로그인' : '회원가입'}</h1></div>
    {signupComplete && mode === 'login' && <div className="success-box"><strong>회원가입이 완료되었습니다.</strong><span>등록한 아이디와 비밀번호로 로그인하세요.</span></div>}
    {mode === 'signup' && <input name="name" placeholder="표시 이름" required/>}
    <input name="login_id" placeholder="아이디" minLength="3" pattern="[a-zA-Z0-9_.-]+" required/>
    {mode === 'signup' && <input name="email" type="email" placeholder="이메일" required/>}
    <input name="password" type="password" placeholder="비밀번호 (8자 이상)" minLength="8" required/>
    <button className="primary" disabled={busy}>{busy ? '처리 중...' : mode === 'login' ? '로그인' : '가입 완료'}</button>
    <button type="button" className="link" onClick={switchMode}>{mode === 'login' ? '계정 만들기' : '로그인으로 돌아가기'}</button>
  </form></main>
}
