import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createProject, listProjects } from '../api/project'

export function useProjectsQuery(notify) {
  const queryClient = useQueryClient()
  const projectsQuery = useQuery({ queryKey: ['projects'], queryFn: listProjects })
  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: project => {
      queryClient.setQueryData(['projects'], current => [project, ...(current ?? [])])
      notify('success', '프로젝트 생성 완료', `${project.name} 프로젝트를 만들었습니다.`)
    },
    onError: error => notify('error', '프로젝트 생성 실패', error.message),
  })
  return { projects: projectsQuery.data ?? [], loading: projectsQuery.isPending, error: projectsQuery.error, createMutation }
}
