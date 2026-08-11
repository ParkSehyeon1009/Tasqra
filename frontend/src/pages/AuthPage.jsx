import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { login, signup } from '../api/auth'
import Logo from '../components/common/Logo'
import '../styles/auth.css'
import '../styles/auth-extras.css'

const FALLBACK_ERROR = '요청 처리 중 오류가 발생했습니다.'

export default function AuthPage({ mode, onAuthenticated, notify }) {
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  async function submit(event) {
    event.preventDefault(); setBusy(true)
    const form = event.currentTarget
    try {
      if (mode === 'signup') {
        await signup(Object.fromEntries(new FormData(form)))
        notify('success', '회원가입 완료', '가입이 완료되었습니다. 아이디로 로그인해 주세요.')
        navigate('/login', { replace: true, state: { signupComplete: true } })
        return
      }
      const result = await login(Object.fromEntries(new FormData(form)))
      onAuthenticated(result)
      notify('success', '로그인 완료', `${result.user.name}님, 환영합니다.`)
      navigate(location.state?.from || '/projects', { replace: true })
    } catch (error) { notify('error', '요청 실패', error.message || FALLBACK_ERROR) }
    finally { setBusy(false) }
  }

  const isSignup = mode === 'signup'
  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}>
    <Link to="/" className="logo-link"><Logo/></Link><div><p className="eyebrow">DOCUMENT WORKSPACE</p><h1>{isSignup ? '회원가입' : '로그인'}</h1></div>
    {!isSignup && location.state?.loginRequired && <div className="login-notice"><strong>로그인이 필요한 기능입니다.</strong><span>프로젝트 작업을 계속하려면 로그인하세요.</span></div>}
    {!isSignup && location.state?.signupComplete && <div className="success-box"><strong>회원가입이 완료되었습니다.</strong><span>등록한 아이디와 비밀번호로 로그인하세요.</span></div>}
    {isSignup && <input name="name" placeholder="표시 이름" required/>}
    <input name="login_id" placeholder="아이디" minLength="3" pattern="[a-zA-Z0-9_.-]+" required/>
    {isSignup && <input name="email" type="email" placeholder="이메일" required/>}
    <input name="password" type="password" placeholder="비밀번호 (8자 이상)" minLength="8" required/>
    <button className="primary" disabled={busy}>{busy ? '처리 중...' : isSignup ? '가입 완료' : '로그인'}</button>
    <Link className="link auth-link" to={isSignup ? '/login' : '/signup'}>{isSignup ? '로그인으로 돌아가기' : '계정 만들기'}</Link>
  </form></main>
}
