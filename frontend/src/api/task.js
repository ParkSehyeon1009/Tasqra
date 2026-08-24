import { http } from './http'

export async function listTasks(projectId) { return (await http.get(`/api/projects/${projectId}/tasks`)).data }
export async function createTask(projectId, payload) { return (await http.post(`/api/projects/${projectId}/tasks`, payload)).data }
export async function updateTask(projectId, taskId, payload) { return (await http.patch(`/api/projects/${projectId}/tasks/${taskId}`, payload)).data }
export async function deleteTask(projectId, taskId) { await http.delete(`/api/projects/${projectId}/tasks/${taskId}`) }
