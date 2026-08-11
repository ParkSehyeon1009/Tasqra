import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { acceptInvitation, declineInvitation, listMyInvitations, listRecentInvitees } from '../api/project'

export function useInvitationsQuery(enabled, notify) {
  const queryClient = useQueryClient()
  const invitationsQuery = useQuery({ queryKey: ['invitations'], queryFn: listMyInvitations, enabled })
  const recentQuery = useQuery({ queryKey: ['recent-invitees'], queryFn: listRecentInvitees, enabled })

  const respond = useMutation({
    mutationFn: ({ id, action }) => action === 'accept' ? acceptInvitation(id) : declineInvitation(id),
    onSuccess: (_, values) => {
      queryClient.setQueryData(['invitations'], current => current?.filter(item => item.id !== values.id))
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      notify?.('success', values.action === 'accept' ? '초대 수락 완료' : '초대 거절 완료', values.action === 'accept' ? '프로젝트에 참여했습니다.' : '프로젝트 초대를 거절했습니다.')
    },
    onError: error => notify?.('error', '초대 처리 실패', error.message),
  })

  return {
    invitations: invitationsQuery.data ?? [],
    recentInvitees: recentQuery.data ?? [],
    responding: respond.isPending,
    accept: id => respond.mutate({ id, action: 'accept' }),
    decline: id => respond.mutate({ id, action: 'decline' }),
  }
}
