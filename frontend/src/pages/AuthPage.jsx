// =============================================================================
// 이 파일의 책임: 로그인과 회원가입 폼을 같은 브랜드 화면에서 제공한다.
// 다른 파일과의 관계: auth API와 세션 훅을 연결하고 성공 후 보호 라우트로 이동한다.
// Spring 비교: 로그인 DTO를 받는 인증 Controller의 입력 View에 해당한다.
// =============================================================================

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
  return <main className="auth-shell">
    <section className="auth-brand" aria-label="Tasqra 소개">
      <Link to="/" className="auth-brand__logo"><Logo/></Link>
      <div className="auth-brand__copy"><p className="eyebrow">DOCUMENT TO PROJECT</p><h1>문서의 맥락을 잃지 않고<br/>실행까지 연결하세요.</h1><p>OCR 검수, AI 분석, 프로젝트 업무와 산출물을 하나의 흐름으로 관리합니다.</p></div>
      <div className="auth-brand__visual" aria-hidden="true"><span>T</span><i/><i/><b>DOC</b><b>AI</b><b>TASK</b></div>
      <ul><li>원문과 분석 근거 연결</li><li>프로젝트별 안전한 권한 관리</li><li>검토와 변경 이력 보존</li></ul>
    </section>
    <section className="auth-form-side">
      <form className="auth-card" onSubmit={submit}>
        <Link to="/" className="auth-mobile-logo"><Logo/></Link>
        <div className="auth-card__heading"><p className="eyebrow">WELCOME TO TASQRA</p><h2>{isSignup ? '새 계정 만들기' : '다시 만나 반가워요.'}</h2><p>{isSignup ? '팀의 문서 업무를 정리할 계정을 만드세요.' : '계정으로 로그인하고 오늘의 프로젝트를 확인하세요.'}</p></div>
        {!isSignup && location.state?.loginRequired && <div className="login-notice"><strong>로그인이 필요한 기능입니다.</strong><span>프로젝트 작업을 계속하려면 로그인하세요.</span></div>}
        {!isSignup && location.state?.signupComplete && <div className="success-box"><strong>회원가입이 완료되었습니다.</strong><span>등록한 아이디와 비밀번호로 로그인하세요.</span></div>}
        <div className="auth-fields">
          {isSignup && <label><span>표시 이름</span><input name="name" placeholder="이름을 입력하세요" autoComplete="name" required/></label>}
          <label><span>아이디</span><input name="login_id" placeholder="아이디를 입력하세요" autoComplete="username" minLength="3" pattern="[a-zA-Z0-9_.-]+" required/></label>
          {isSignup && <label><span>이메일</span><input name="email" type="email" placeholder="name@example.com" autoComplete="email" required/></label>}
          <label><span>비밀번호</span><input name="password" type="password" placeholder="8자 이상 입력하세요" autoComplete={isSignup ? 'new-password' : 'current-password'} minLength="8" required/></label>
        </div>
        <button className="primary auth-submit" disabled={busy}>{busy ? '처리 중...' : isSignup ? '계정 만들기' : '로그인'}</button>
        <p className="auth-switch">{isSignup ? '이미 계정이 있으신가요?' : '아직 계정이 없으신가요?'} <Link to={isSignup ? '/login' : '/signup'}>{isSignup ? '로그인' : '회원가입'}</Link></p>
      </form>
    </section>
  </main>
}
