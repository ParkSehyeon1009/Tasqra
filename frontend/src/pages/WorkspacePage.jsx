import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { getProject } from '../api/project'
import AppHeader from '../components/common/AppHeader'
import LoadingState from '../components/common/LoadingState'
import BoardView from '../features/board/BoardView'
import DashboardView from '../features/dashboard/DashboardView'
import DocumentsView from '../features/documents/DocumentsView'
import DocumentUploadOptionsDialog from '../features/documents/DocumentUploadOptionsDialog'
import MembersView from '../features/members/MembersView'
import { useProjectsQuery } from '../hooks/useProjectsQuery'
import { useWorkspaceData } from '../hooks/useWorkspaceData'
import '../styles/workspace.css'

const TABS = [['dashboard','대시보드'],['documents','문서'],['board','보드'],['settings','설정']]

export default function WorkspacePage({ user, onLogout, notify }) {
  const { projectId, tab } = useParams()
  const navigate = useNavigate()
  const projectQuery = useQuery({
    queryKey: ['project-access', projectId],
    queryFn: () => getProject(projectId),
    retry: false,
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
    refetchInterval: 3_000,
  })
  const { deleteMutation } = useProjectsQuery(notify)
  const project = projectQuery.data
  if (!TABS.some(([key]) => key === tab)) return <Navigate to={`/projects/${projectId}/documents`} replace/>
  if (projectQuery.isPending) return <LoadingState label="프로젝트 접근 권한을 확인하는 중..."/>
  if (projectQuery.isError || !project) return <Navigate to="/projects" replace/>
  return <WorkspaceContent project={project} tab={tab} navigate={navigate} notify={notify} user={user} onLogout={onLogout} deleteMutation={deleteMutation}/>
}

function WorkspaceContent({ project, tab, navigate, notify, user, onLogout, deleteMutation }) {
  const data = useWorkspaceData(project, notify)
  const fileInputRef = useRef(null)
  const [pendingFile, setPendingFile] = useState(null)
  const canEdit = project.role !== 'VIEWER'
  const openUpload = () => fileInputRef.current?.click()
  function requestUpload(file) {
    if (!file || !canEdit) return
    const extension = file.name.split('.').pop()?.toLowerCase()
    if (extension === 'docx' || extension === 'hwpx') {
      setPendingFile(file)
      return
    }
    return data.uploadFile(file, 'AUTO')
  }
  async function upload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    try { await requestUpload(file) } catch { /* 공통 토스트에서 처리 */ }
    finally { event.target.value = '' }
  }
  async function confirmDocumentUpload(extractionStrategy) {
    try { await data.uploadFile(pendingFile, extractionStrategy); setPendingFile(null) } catch { /* 공통 토스트에서 처리 */ }
  }
  async function deleteCurrentProject() {
    try {
      await deleteMutation.mutateAsync(project.id)
      navigate('/projects', { replace: true })
    } catch { /* 공통 토스트에서 처리 */ }
  }
  return <div className="app-frame"><AppHeader user={user} onLogout={onLogout} notify={notify} project={project}/><input ref={fileInputRef} hidden type="file" accept=".pdf,.docx,.hwpx,.png,.jpg,.jpeg" onChange={upload}/>
    <nav className="tabs">{TABS.map(([key,label]) => <button className={tab === key ? 'active' : ''} onClick={() => navigate(`/projects/${project.id}/${key}`)} key={key}>{label}</button>)}</nav>
    <main className="workspace-main">{data.loading ? <LoadingState label="프로젝트 데이터를 불러오는 중..."/> : <TabContent tab={tab} project={project} data={data} canEdit={canEdit} onUpload={openUpload} onFileDrop={requestUpload} uploading={data.uploading} onDeleteProject={deleteCurrentProject} deleting={deleteMutation.isPending}/>}</main>
    <DocumentUploadOptionsDialog file={pendingFile} uploading={data.uploading} onCancel={() => setPendingFile(null)} onConfirm={confirmDocumentUpload}/>
  </div>
}

function TabContent({ tab, project, data, canEdit, onUpload, onFileDrop, uploading, onDeleteProject, deleting }) {
  if (tab === 'documents') return <DocumentsView projectId={project.id} documents={data.documents} canEdit={canEdit} onUpload={onUpload} onFileDrop={onFileDrop} uploading={uploading} uploadingFileName={data.uploadingFileName}/>
  if (tab === 'settings') return <MembersView project={project} members={data.members} invitations={data.invitations} onUpdateProject={data.updateProject} updatingProject={data.updatingProject} onInvite={data.invite} onCancelInvitation={data.cancelInvitation} onRole={data.changeRole} onRemove={data.excludeMember} onDeleteProject={onDeleteProject} deleting={deleting}/>
  if (tab === 'dashboard') return <DashboardView documents={data.documents} members={data.members}/>
  return <BoardView/>
}
