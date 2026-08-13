const keyFor = userId => `tasqra:last-project:${userId}`

export function getRecentProjectId(userId) {
  if (!userId) return null
  return localStorage.getItem(keyFor(userId))
}

export function setRecentProjectId(userId, projectId) {
  if (!userId || !projectId) return
  localStorage.setItem(keyFor(userId), String(projectId))
}

export function clearRecentProjectId(userId, projectId) {
  if (!userId) return
  const key = keyFor(userId)
  if (!projectId || localStorage.getItem(key) === String(projectId)) localStorage.removeItem(key)
}
