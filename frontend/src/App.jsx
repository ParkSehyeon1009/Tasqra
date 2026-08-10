import AuthPage from './pages/AuthPage'
import ProjectsPage from './pages/ProjectsPage'
import WorkspacePage from './pages/WorkspacePage'
import Toast from './components/common/Toast'
import { useSession } from './hooks/useSession'
import { useToast } from './hooks/useToast'
import './styles/app.css'

export default function App() {
  const { toast, notify, closeToast } = useToast()
  const session = useSession(notify)

  if (session.loading) return <div className="center">Tasqra를 불러오는 중...</div>

  return <>
    <Toast toast={toast} onClose={closeToast}/>
    {!session.user ? (
      <AuthPage onAuthenticated={session.login} notify={notify}/>
    ) : session.selectedProject ? (
      <WorkspacePage project={session.selectedProject} onBack={session.closeProject} notify={notify}/>
    ) : (
      <ProjectsPage
        user={session.user}
        projects={session.projects}
        onCreate={session.createProject}
        onSelect={session.openProject}
        onLogout={session.logout}
      />
    )}
  </>
}
