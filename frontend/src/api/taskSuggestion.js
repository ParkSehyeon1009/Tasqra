import { http } from './http'

const list = async (projectId, state, documentId) => (await http.get(
  `/api/projects/${projectId}/task-suggestions${state ? `/${state}` : ''}`,
  { params: { document_id: documentId, limit: 200 } },
)).data

export const getTaskSuggestions = (projectId, documentId) => list(projectId, '', documentId)
export const getPendingTaskSuggestions = (projectId, documentId) => list(projectId, 'pending', documentId)
export const getRejectedTaskSuggestions = (projectId, documentId) => list(projectId, 'rejected', documentId)
export const approveTaskSuggestion = async (projectId, id, changes = {}) =>
  (await http.post(`/api/projects/${projectId}/task-suggestions/${id}/approve`, changes)).data
export const rejectTaskSuggestion = async (projectId, id) =>
  (await http.post(`/api/projects/${projectId}/task-suggestions/${id}/reject`)).data
