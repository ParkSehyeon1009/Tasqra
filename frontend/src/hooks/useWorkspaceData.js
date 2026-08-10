import { useEffect, useRef, useState } from 'react'
import { addMember, listMembers, listProjectDocuments, removeMember, updateMember, uploadProjectDocument } from '../api/project'

const FALLBACK_ERROR = '요청 처리 중 오류가 발생했습니다.'

export function useWorkspaceData(project, notify) {
  const [members, setMembers] = useState([])
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const fileInputRef = useRef(null)

  useEffect(() => {
    Promise.all([listMembers(project.id), listProjectDocuments(project.id)])
      .then(([nextMembers, nextDocuments]) => { setMembers(nextMembers); setDocuments(nextDocuments.items) })
      .catch(error => notify('error', '불러오기 실패', error.message || FALLBACK_ERROR))
      .finally(() => setLoading(false))
  }, [project.id, notify])

  async function invite(event) {
    event.preventDefault()
    const form = event.currentTarget
    try {
      const member = await addMember(project.id, Object.fromEntries(new FormData(form)))
      setMembers(current => [...current, member]); form.reset()
      notify('success', '팀원 추가 완료', `${member.name}님을 ${member.role} 권한으로 추가했습니다.`)
    } catch (error) { notify('error', '팀원 추가 실패', error.message || FALLBACK_ERROR) }
  }

  async function changeRole(member, role) {
    const previous = members
    setMembers(current => current.map(item => item.user_id === member.user_id ? { ...item, role } : item))
    try {
      await updateMember(project.id, member.user_id, role)
      notify('success', '권한 변경 완료', `${member.name}님의 권한을 ${role}로 변경했습니다.`)
    } catch (error) {
      setMembers(previous); notify('error', '권한 변경 실패', error.message || FALLBACK_ERROR)
    }
  }

  async function excludeMember(member) {
    const previous = members
    setMembers(current => current.filter(item => item.user_id !== member.user_id))
    try {
      await removeMember(project.id, member.user_id)
      notify('success', '팀원 제외 완료', `${member.name}님을 프로젝트에서 제외했습니다.`)
    } catch (error) {
      setMembers(previous); notify('error', '팀원 제외 실패', error.message || FALLBACK_ERROR)
    }
  }

  async function upload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const document = await uploadProjectDocument(project.id, file)
      setDocuments(current => [document, ...current])
      notify('success', '문서 업로드 완료', `${document.filename} 처리가 완료되었습니다.`)
    } catch (error) { notify('error', '문서 업로드 실패', error.message || FALLBACK_ERROR) }
    finally { event.target.value = '' }
  }

  return { members, documents, loading, fileInputRef, invite, changeRole, excludeMember, upload }
}
