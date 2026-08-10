import { http } from './http'

export async function listProjects() { return (await http.get('/api/projects')).data }
export async function createProject(payload) { return (await http.post('/api/projects', payload)).data }
export async function listMembers(projectId) { return (await http.get(`/api/projects/${projectId}/members`)).data }
export async function addMember(projectId, payload) { return (await http.post(`/api/projects/${projectId}/members`, payload)).data }
export async function updateMember(projectId, userId, role) { return (await http.patch(`/api/projects/${projectId}/members/${userId}`, { role })).data }
export async function removeMember(projectId, userId) { await http.delete(`/api/projects/${projectId}/members/${userId}`) }
export async function listProjectDocuments(projectId) { return (await http.get(`/api/projects/${projectId}/documents`)).data }
export async function uploadProjectDocument(projectId, file) {
  const body = new FormData(); body.append('file', file)
  return (await http.post(`/api/projects/${projectId}/documents`, body)).data
}
