// =============================================================================
// 이 파일의 책임: 내 프로젝트 초대·최근 초대 대상 조회와 초대 응답 mutation을 묶는다.
// 다른 파일과의 관계: project API를 호출하고 프로젝트·포트폴리오 캐시를 갱신한다.
// Spring 비교: React Query 기반 조회 Service와 mutation 이벤트 핸들러에 해당한다.
// =============================================================================

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { acceptInvitation, declineInvitation, listMyInvitations, listRecentInvitees } from '../api/project'

export function useInvitationsQuery(userId, notify) {
  const queryClient = useQueryClient()
  const invitationsKey = ['invitations', userId]
  const recentInviteesKey = ['recent-invitees', userId]
  const enabled = Boolean(userId)
  const invitationsQuery = useQuery({
    queryKey: invitationsKey,
    queryFn: listMyInvitations,
    enabled,
    refetchInterval: 5_000,
    refetchOnMount: 'always',
    refetchOnWindowFocus: true,
  })
  const recentQuery = useQuery({ queryKey: recentInviteesKey, queryFn: listRecentInvitees, enabled })

  const respond = useMutation({
    mutationFn: ({ id, action }) => action === 'accept' ? acceptInvitation(id) : declineInvitation(id),
    onSuccess: (_, values) => {
      queryClient.setQueryData(invitationsKey, current => current?.filter(item => item.id !== values.id))
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      if (values.action === 'accept') {
        queryClient.invalidateQueries({ queryKey: ['portfolio-dashboard', userId] })
      }
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
