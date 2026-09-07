// =============================================================================
// 이 파일의 책임: 인증 상태에 따라 공개·보호 라우트를 조립하고 프로젝트 공통
//   도구를 페이지 전환과 독립된 수명으로 제공한다.
// 다른 파일과의 관계: 각 page를 라우팅하고, 프로젝트 경로에서는 ChatView를 한 번만
//   마운트해 작업공간·문서 상세·OCR 검수 사이에서도 진행 상태를 유지한다.
// Spring 비교: SecurityFilter와 공통 Layout Controller를 합친 애플리케이션 진입점이다.
// =============================================================================

import { useQuery } from '@tanstack/react-query'
import { Navigate, Route, Routes, useLocation, useMatch } from 'react-router-dom'
import { getProject } from './api/project'
import Toast from './components/common/Toast'
import ChatView from './features/chat/ChatView'
import { useSession } from './hooks/useSession'
import { useToast } from './hooks/useToast'
import AuthPage from './pages/AuthPage'
import LandingPage from './pages/LandingPage'
import NotFoundPage from './pages/NotFoundPage'
import ProjectsPage from './pages/ProjectsPage'
import WorkspacePage from './pages/WorkspacePage'
import OcrReviewPage from './pages/OcrReviewPage'
import DocumentDetailPage from './pages/DocumentDetailPage'
import './styles/app.css'
import './styles/states.css'
import './styles/responsive.css'
import './styles/design-refresh.css'
import './styles/unified-ui.css'
import { applyThemeColor, getSavedThemeColor } from './utils/theme'

applyThemeColor(getSavedThemeColor())

function ProtectedRoute({ user, loading, children }) {
  const location = useLocation()
  if (loading) return <div className="center">Tasqra를 불러오는 중...</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname, loginRequired: true }}/>
  return children
}

function ProjectChatHost({ user }) {
  const match = useMatch('/projects/:projectId/*')
  const rawProjectId = match?.params.projectId
  const projectId = Number(rawProjectId)
  const enabled = Boolean(user && Number.isSafeInteger(projectId) && projectId > 0)
  const projectQuery = useQuery({
    queryKey: ['project-access', rawProjectId],
    queryFn: () => getProject(rawProjectId),
    enabled,
    retry: false,
  })

  if (!enabled || !projectQuery.data) return null
  return <ChatView key={projectId} projectId={projectId} projectName={projectQuery.data.name}/>
}

export default function App() {
  const { toast, notify, closeToast } = useToast()
  const session = useSession()

  return <>
    <Toast toast={toast} onClose={closeToast}/>
    <Routes>
      <Route path="/" element={<LandingPage user={session.user} onLogout={session.logout} notify={notify}/>}/>
      <Route path="/login" element={session.user ? <Navigate to="/projects" replace/> : <AuthPage mode="login" onAuthenticated={session.login} notify={notify}/>}/>
      <Route path="/signup" element={session.user ? <Navigate to="/projects" replace/> : <AuthPage mode="signup" onAuthenticated={session.login} notify={notify}/>}/>
      <Route path="/projects" element={<ProtectedRoute {...session}><ProjectsPage user={session.user} onLogout={session.logout} notify={notify}/></ProtectedRoute>}/>
      <Route path="/projects/:projectId" element={<Navigate to="dashboard" replace/>}/>
      <Route path="/projects/:projectId/documents/:documentId" element={<ProtectedRoute {...session}><DocumentDetailPage user={session.user} onLogout={session.logout} notify={notify}/></ProtectedRoute>}/>
      <Route path="/projects/:projectId/documents/:documentId/review" element={<ProtectedRoute {...session}><OcrReviewPage user={session.user} onLogout={session.logout} notify={notify}/></ProtectedRoute>}/>
      <Route path="/projects/:projectId/:tab" element={<ProtectedRoute {...session}><WorkspacePage user={session.user} onLogout={session.logout} notify={notify}/></ProtectedRoute>}/>
      <Route path="*" element={<NotFoundPage/>}/>
    </Routes>
    <ProjectChatHost user={session.user}/>
  </>
}
