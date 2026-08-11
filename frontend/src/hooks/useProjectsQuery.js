import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createProject, inviteMember, listProjects } from '../api/project'

export function useProjectsQuery(notify) {
  const queryClient = useQueryClient()
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: listProjects })
  const createMutation = useMutation({
    mutationFn: async ({ project: values, invitations = [] }) => {
      const project = await createProject(values)
      const results = await Promise.allSettled(invitations.map(item => inviteMember(project.id, item)))
      return { project, failedInvitations: results.filter(result => result.status === 'rejected').length }
    },
    onSuccess: ({ project, failedInvitations }) => {
      queryClient.setQueryData(['projects'], current => [project, ...(current ?? [])])
      queryClient.invalidateQueries({ queryKey: ['recent-invitees'] })
      notify(failedInvitations ? 'error' : 'success', failedInvitations ? '프로젝트 생성 완료 · 일부 초대 실패' : '프로젝트 생성 완료', failedInvitations ? `${project.name} 프로젝트는 생성됐지만 ${failedInvitations}명의 초대를 보내지 못했습니다.` : `${project.name} 프로젝트를 만들었습니다.`)
    },
    onError: error => notify('error', '프로젝트 생성 실패', error.message),
  })
  return { projects: projectsQuery.data ?? [], loading: projectsQuery.isPending, error: projectsQuery.error, createMutation }
}
