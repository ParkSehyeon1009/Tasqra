// =============================================================================
// 이 파일의 책임: 워크스페이스의 멤버·문서·초대 조회와 변경 mutation을 묶는다.
// 다른 파일과의 관계: WorkspacePage가 URL 문서 유형을 넘기고, api/document.js의
//   서버 필터 응답을 유형별 React Query 캐시에 저장한다.
// Spring 비교: 여러 Application Service 호출을 화면 단위로 조합하는 Facade에 가깝다.
// =============================================================================

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cancelProjectInvitation, inviteMember, listMembers, listProjectInvitations, removeMember, updateMember, updateProject, uploadProjectDocument } from '../api/project'
import { listDocuments, retryDocumentProcessing } from '../api/document'

const FALLBACK_ERROR = '요청 처리 중 오류가 발생했습니다.'

export function useWorkspaceData(project, notify, { documentType = '', documentState = '' } = {}) {
  const queryClient = useQueryClient()
  const membersKey = ['projects', project.id, 'members']
  const documentsPrefix = ['projects', project.id, 'documents']
  const documentsKey = [...documentsPrefix, documentType || 'all', documentState || 'all']
  const invitationsKey = ['projects', project.id, 'invitations']
  const membersQuery = useQuery({ queryKey: membersKey, queryFn: () => listMembers(project.id) })
  const documentsQuery = useQuery({
    queryKey: documentsKey,
    queryFn: () => listDocuments(project.id, { documentType, documentState }),
    refetchInterval: query => query.state.data?.items?.some(item => ['PENDING', 'EXTRACTING'].includes(item.status)) ? 3_000 : false,
  })
  const invitationsQuery = useQuery({ queryKey: invitationsKey, queryFn: () => listProjectInvitations(project.id), enabled: project.role === 'OWNER' })

  const projectMutation = useMutation({
    mutationFn: values => updateProject(project.id, values),
    onSuccess: updated => {
      queryClient.setQueryData(['project-access', String(project.id)], updated)
      queryClient.setQueryData(['projects'], current => current?.map(item => item.id === updated.id ? updated : item))
      notify('success', '프로젝트 정보 수정 완료', '변경한 프로젝트 정보를 저장했습니다.')
    },
    onError: error => notify('error', '프로젝트 정보 수정 실패', error.message || FALLBACK_ERROR),
  })
  const inviteMutation = useMutation({
    mutationFn: values => inviteMember(project.id, values),
    onSuccess: invitation => {
      queryClient.setQueryData(invitationsKey, current => [invitation, ...(current ?? []).filter(item => item.id !== invitation.id)])
      queryClient.invalidateQueries({ queryKey: ['recent-invitees'] })
      notify('success', '초대 전송 완료', `${invitation.invitee_name}님에게 프로젝트 초대를 보냈습니다.`)
    },
    onError: error => notify('error', '초대 전송 실패', error.message || FALLBACK_ERROR),
  })
  const cancelInvitationMutation = useMutation({
    mutationFn: invitation => cancelProjectInvitation(project.id, invitation.id),
    onSuccess: (_, invitation) => {
      queryClient.setQueryData(invitationsKey, current => current?.map(item => item.id === invitation.id ? { ...item, status: 'CANCELED' } : item))
      notify('success', '초대 취소 완료', `${invitation.invitee_name}님에게 보낸 초대를 취소했습니다.`)
    },
    onError: error => notify('error', '초대 취소 실패', error.message || FALLBACK_ERROR),
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
    mutationFn: ({ file, extractionStrategy, documentType }) => uploadProjectDocument(project.id, file, extractionStrategy, documentType),
    onSuccess: document => {
      // 유형별 목록 캐시가 나뉘므로 현재 화면 하나에 억지로 끼워 넣지 않는다.
      // 프로젝트의 모든 문서 목록을 무효화해 각 필터가 서버 기준으로 다시 세게 한다.
      queryClient.invalidateQueries({ queryKey: documentsPrefix })
      queryClient.invalidateQueries({ queryKey: ['projects', project.id, 'dashboard'] })
      notify('success', '문서 업로드 접수', `${document.filename} 처리를 시작했습니다.`)
    },
    onError: error => notify('error', '문서 업로드 실패', error.message || FALLBACK_ERROR),
  })
  const retryDocumentMutation = useMutation({
    mutationFn: document => retryDocumentProcessing(project.id, document.id),
    onSuccess: (_, document) => {
      queryClient.invalidateQueries({ queryKey: documentsPrefix })
      queryClient.invalidateQueries({ queryKey: ['projects', project.id, 'dashboard'] })
      notify('success', '문서 재처리 접수', `${document.filename} 처리를 다시 시작했습니다.`)
    },
    onError: error => notify('error', '문서 재처리 실패', error.message || FALLBACK_ERROR),
  })

  async function invite(event) {
    event.preventDefault()
    const form = event.currentTarget
    try { await inviteMutation.mutateAsync(Object.fromEntries(new FormData(form))); form.reset() } catch { /* 공통 토스트에서 처리 */ }
  }

  return {
    members: membersQuery.data ?? [], documents: documentsQuery.data?.items ?? [], documentsTotal: documentsQuery.data?.total ?? 0, invitations: invitationsQuery.data ?? [],
    loading: membersQuery.isPending || documentsQuery.isPending,
    error: membersQuery.error || documentsQuery.error,
    invite, cancelInvitation: invitation => cancelInvitationMutation.mutate(invitation),
    updateProject: values => projectMutation.mutateAsync(values), updatingProject: projectMutation.isPending,
    changeRole: (member, role) => roleMutation.mutate({ member, role }),
    excludeMember: member => removeMutation.mutate(member),
    uploadFile: (file, extractionStrategy = 'AUTO', documentType = null) => uploadMutation.mutateAsync({ file, extractionStrategy, documentType }),
    retryDocument: document => retryDocumentMutation.mutate(document),
    retryingDocumentId: retryDocumentMutation.variables?.id ?? null,
    uploading: uploadMutation.isPending,
    uploadingFileName: uploadMutation.variables?.file?.name ?? null,
  }
}
