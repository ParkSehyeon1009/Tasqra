import { http } from './http'

export async function listProjects() { return (await http.get('/api/projects')).data }
export async function createProject(payload) { return (await http.post('/api/projects', payload)).data }
export async function listMembers(projectId) { return (await http.get(`/api/projects/${projectId}/members`)).data }
export async function addMember(projectId, payload) { return (await http.post(`/api/projects/${projectId}/members`, payload)).data }
export async function inviteMember(projectId, payload) { return (await http.post(`/api/projects/${projectId}/invitations`, payload)).data }
export async function listProjectInvitations(projectId) { return (await http.get(`/api/projects/${projectId}/invitations`)).data }
export async function listMyInvitations() { return (await http.get('/api/invitations')).data }
export async function listRecentInvitees() { return (await http.get('/api/invitations/recent-invitees')).data }
export async function acceptInvitation(invitationId) { await http.post(`/api/invitations/${invitationId}/accept`) }
export async function declineInvitation(invitationId) { await http.post(`/api/invitations/${invitationId}/decline`) }
export async function updateMember(projectId, userId, role) { return (await http.patch(`/api/projects/${projectId}/members/${userId}`, { role })).data }
export async function removeMember(projectId, userId) { await http.delete(`/api/projects/${projectId}/members/${userId}`) }
export async function listProjectDocuments(projectId) { return (await http.get(`/api/projects/${projectId}/documents`)).data }
export async function uploadProjectDocument(projectId, file) {
  const body = new FormData(); body.append('file', file)
  return (await http.post(`/api/projects/${projectId}/documents`, body)).data
}
