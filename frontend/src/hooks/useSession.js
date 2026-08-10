import { useEffect, useState } from 'react'
import { getMe } from '../api/auth'
import { createProject as requestCreateProject, listProjects } from '../api/project'

const FALLBACK_ERROR = '요청 처리 중 오류가 발생했습니다.'

export function useSession(notify) {
  const [user, setUser] = useState(null)
  const [projects, setProjects] = useState([])
  const [selectedProject, setSelectedProject] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('tasqra_token')
    if (!token) {
      queueMicrotask(() => setLoading(false))
      return
    }
    getMe()
      .then(account => Promise.all([account, listProjects()]))
      .then(([account, rows]) => { setUser(account); setProjects(rows) })
      .catch(() => localStorage.removeItem('tasqra_token'))
      .finally(() => setLoading(false))
  }, [])

  async function login(account) {
    setUser(account)
    try { setProjects(await listProjects()) }
    catch (error) { notify('error', '프로젝트 조회 실패', error.message || FALLBACK_ERROR) }
  }

  async function createProject(event) {
    event.preventDefault()
    const form = event.currentTarget
    try {
      const project = await requestCreateProject(Object.fromEntries(new FormData(form)))
      setProjects(current => [project, ...current])
      form.reset(); setSelectedProject(project)
      notify('success', '프로젝트 생성 완료', `${project.name} 프로젝트를 만들었습니다.`)
      return true
    } catch (error) {
      notify('error', '프로젝트 생성 실패', error.message || FALLBACK_ERROR)
      return false
    }
  }

  function logout() {
    localStorage.removeItem('tasqra_token')
    setUser(null); setProjects([]); setSelectedProject(null)
  }

  return {
    user, projects, selectedProject, loading,
    login, logout, createProject,
    openProject: setSelectedProject,
    closeProject: () => setSelectedProject(null),
  }
}
