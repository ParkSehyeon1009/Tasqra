import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { inviteMember, listMembers, listProjectDocuments, removeMember, updateMember, uploadProjectDocument } from '../api/project'

const FALLBACK_ERROR = '요청 처리 중 오류가 발생했습니다.'

export function useWorkspaceData(project, notify) {
  const queryClient = useQueryClient()
  const membersKey = ['projects', project.id, 'members']
  const documentsKey = ['projects', project.id, 'documents']
  const membersQuery = useQuery({ queryKey: membersKey, queryFn: () => listMembers(project.id) })
  const documentsQuery = useQuery({ queryKey: documentsKey, queryFn: () => listProjectDocuments(project.id) })

  const inviteMutation = useMutation({
    mutationFn: values => inviteMember(project.id, values),
    onSuccess: invitation => {
      queryClient.invalidateQueries({ queryKey: ['recent-invitees'] })
      notify('success', '초대 전송 완료', `${invitation.invitee_name}님에게 프로젝트 초대를 보냈습니다.`)
    },
    onError: error => notify('error', '초대 전송 실패', error.message || FALLBACK_ERROR),
  })
  const roleMutation = useMutation({
    mutationFn: ({ member, role }) => updateMember(project.id, member.user_id, role),
    onMutate: async ({ member, role }) => {
      await queryClient.cancelQueries({ queryKey: membersKey })
      const previous = queryClient.getQueryData(membersKey)
      queryClient.setQueryData(membersKey, current => current?.map(item => item.user_id === member.user_id ? { ...item, role } : item))
      return { previous }
    },
    onSuccess: (updated, { member }) => notify('success', '권한 변경 완료', `${member.name}님의 권한을 ${updated.role}로 변경했습니다.`),
    onError: (error, _, context) => { queryClient.setQueryData(membersKey, context?.previous); notify('error', '권한 변경 실패', error.message || FALLBACK_ERROR) },
  })
  const removeMutation = useMutation({
    mutationFn: member => removeMember(project.id, member.user_id),
    onMutate: async member => {
      await queryClient.cancelQueries({ queryKey: membersKey })
      const previous = queryClient.getQueryData(membersKey)
      queryClient.setQueryData(membersKey, current => current?.filter(item => item.user_id !== member.user_id))
      return { previous }
    },
    onSuccess: (_, member) => notify('success', '팀원 제외 완료', `${member.name}님을 프로젝트에서 제외했습니다.`),
    onError: (error, _, context) => { queryClient.setQueryData(membersKey, context?.previous); notify('error', '팀원 제외 실패', error.message || FALLBACK_ERROR) },
  })
  const uploadMutation = useMutation({
    mutationFn: file => uploadProjectDocument(project.id, file),
    onSuccess: document => {
      queryClient.setQueryData(documentsKey, current => ({ ...(current ?? {}), items: [document, ...(current?.items ?? [])], total: (current?.total ?? 0) + 1 }))
      notify('success', '문서 업로드 완료', `${document.filename} 처리가 완료되었습니다.`)
    },
    onError: error => notify('error', '문서 업로드 실패', error.message || FALLBACK_ERROR),
  })

  async function invite(event) {
    event.preventDefault()
    const form = event.currentTarget
    try { await inviteMutation.mutateAsync(Object.fromEntries(new FormData(form))); form.reset() } catch { /* 공통 토스트에서 처리 */ }
  }

  return {
    members: membersQuery.data ?? [], documents: documentsQuery.data?.items ?? [],
    loading: membersQuery.isPending || documentsQuery.isPending,
    error: membersQuery.error || documentsQuery.error,
    invite,
    changeRole: (member, role) => roleMutation.mutate({ member, role }),
    excludeMember: member => removeMutation.mutate(member),
    uploadFile: file => uploadMutation.mutateAsync(file),
  }
}
