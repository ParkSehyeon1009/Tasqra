import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Toast from './components/common/Toast'
import { useSession } from './hooks/useSession'
import { useToast } from './hooks/useToast'
import AuthPage from './pages/AuthPage'
import LandingPage from './pages/LandingPage'
import NotFoundPage from './pages/NotFoundPage'
import ProjectsPage from './pages/ProjectsPage'
import WorkspacePage from './pages/WorkspacePage'
import './styles/app.css'
import './styles/states.css'

function ProtectedRoute({ user, loading, children }) {
  const location = useLocation()
  if (loading) return <div className="center">Tasqra를 불러오는 중...</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname, loginRequired: true }}/>
  return children
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
      <Route path="/projects/:projectId" element={<Navigate to="documents" replace/>}/>
      <Route path="/projects/:projectId/:tab" element={<ProtectedRoute {...session}><WorkspacePage user={session.user} onLogout={session.logout} notify={notify}/></ProtectedRoute>}/>
      <Route path="*" element={<NotFoundPage/>}/>
    </Routes>
  </>
}
