/**
 * Cliente de la API.
 *
 * La sesión viaja en una cookie httponly, así que el navegador la adjunta solo
 * y el token nunca pasa por JavaScript. Un 401 se convierte en un error
 * reconocible para que la app vuelva al login sin adivinar por el mensaje.
 */

export class UnauthorizedError extends Error {
  constructor(message) {
    super(message)
    // Sin esto, name queda en 'Error' y no se puede distinguir por nombre.
    this.name = 'UnauthorizedError'
  }
}

async function request(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, {
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    ...options,
  })

  if (response.status === 401) throw new UnauthorizedError('Sesión expirada')

  if (!response.ok) {
    let detail = `Error ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // Respuesta sin cuerpo JSON: se queda el mensaje genérico.
    }
    throw new Error(detail)
  }

  return response.status === 204 ? null : response.json()
}

export const api = {
  me: () => request('/auth/me'),

  login: (password) =>
    request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  logout: () => request('/auth/logout', { method: 'POST' }),

  tickets: ({ categoryId, search, includeArchived } = {}) => {
    const params = new URLSearchParams({ limit: '200' })
    if (categoryId) params.set('category_id', categoryId)
    if (search) params.set('search', search)
    if (includeArchived) params.set('include_archived', 'true')
    return request(`/tickets?${params}`)
  },

  archiveTicket: (id, resolution) =>
    request(`/tickets/${id}/dispatch`, {
      method: 'POST',
      body: JSON.stringify({ resolution }),
    }),

  updateTicket: (id, cambios) =>
    request(`/tickets/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(cambios),
    }),

  categories: () => request('/categories'),

  createCategory: (name) =>
    request('/categories', { method: 'POST', body: JSON.stringify({ name }) }),

  renameCategory: (id, name) =>
    request(`/categories/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  deleteCategory: (id) => request(`/categories/${id}`, { method: 'DELETE' }),

  // --- Dashboard semanal ---

  threads: () => request('/threads'),

  threadColors: () => request('/threads/colors'),

  createThread: (name, color) =>
    request('/threads', { method: 'POST', body: JSON.stringify({ name, color }) }),

  updateThread: (id, cambios) =>
    request(`/threads/${id}`, { method: 'PATCH', body: JSON.stringify(cambios) }),

  deleteThread: (id) => request(`/threads/${id}`, { method: 'DELETE' }),

  reorderThreads: (ids) =>
    request('/threads/reorder', { method: 'POST', body: JSON.stringify({ ids }) }),

  addTask: (threadId, text) =>
    request(`/threads/${threadId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  reorderTasks: (threadId, ids) =>
    request(`/threads/${threadId}/tasks/reorder`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  updateTask: (taskId, cambios) =>
    request(`/threads/tasks/${taskId}`, {
      method: 'PATCH',
      body: JSON.stringify(cambios),
    }),

  deleteTask: (taskId) => request(`/threads/tasks/${taskId}`, { method: 'DELETE' }),

  cleanupBoard: () => request('/threads/cleanup', { method: 'POST' }),

  chat: (messages) =>
    request('/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ messages }),
    }),
}
