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

  tickets: ({ search, includeArchived } = {}) => {
    const params = new URLSearchParams({ limit: '200' })
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

  // --- Prompts ---

  promptProjects: () => request('/prompts/projects'),

  createProject: (name, description_md) =>
    request('/prompts/projects', {
      method: 'POST',
      body: JSON.stringify({ name, description_md }),
    }),

  updateProject: (id, cambios) =>
    request(`/prompts/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(cambios),
    }),

  deleteProject: (id) =>
    request(`/prompts/projects/${id}`, { method: 'DELETE' }),

  prompts: ({ projectId, sinProyecto } = {}) => {
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (sinProyecto) params.set('sin_proyecto', 'true')
    return request(`/prompts?${params}`)
  },

  updatePrompt: (id, cambios) =>
    request(`/prompts/${id}`, { method: 'PATCH', body: JSON.stringify(cambios) }),

  deletePrompt: (id) => request(`/prompts/${id}`, { method: 'DELETE' }),

  // --- Gastos ---

  expenses: (desde, hasta) =>
    request(`/expenses?desde=${desde}&hasta=${hasta}`),

  expenseSummary: (desde, hasta) =>
    request(`/expenses/summary?desde=${desde}&hasta=${hasta}`),

  createExpense: (datos) =>
    request('/expenses', { method: 'POST', body: JSON.stringify(datos) }),

  updateExpense: (id, cambios) =>
    request(`/expenses/${id}`, { method: 'PATCH', body: JSON.stringify(cambios) }),

  deleteExpense: (id) => request(`/expenses/${id}`, { method: 'DELETE' }),

  expenseCategories: () => request('/expenses/categories'),
  expenseMethods: () => request('/expenses/methods'),

  createSubcategory: (categoryId, name) =>
    request(`/expenses/categories/${categoryId}/subcategories`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  renameSubcategory: (id, name) =>
    request(`/expenses/subcategories/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  deleteSubcategory: (id) =>
    request(`/expenses/subcategories/${id}`, { method: 'DELETE' }),

  createExpenseLabel: (tipo, name) =>
    request(`/expenses/${tipo}`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  renameExpenseLabel: (tipo, id, name) =>
    request(`/expenses/${tipo}/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  deleteExpenseLabel: (tipo, id) =>
    request(`/expenses/${tipo}/${id}`, { method: 'DELETE' }),

  // --- Panel de Tareas ---

  // scope: 'week' (por defecto), 'backlog' u 'all'. `week` acepta cualquier
  // día de la semana pedida; el backend lo normaliza al lunes.
  threads: ({ scope, week } = {}) => {
    const q = new URLSearchParams()
    if (scope) q.set('scope', scope)
    if (week) q.set('week', week)
    const cola = q.toString()
    return request(`/threads${cola ? `?${cola}` : ''}`)
  },

  threadColors: () => request('/threads/colors'),

  createThread: (name, color) =>
    request('/threads', { method: 'POST', body: JSON.stringify({ name, color }) }),

  updateThread: (id, cambios) =>
    request(`/threads/${id}`, { method: 'PATCH', body: JSON.stringify(cambios) }),

  deleteThread: (id) => request(`/threads/${id}`, { method: 'DELETE' }),

  reorderThreads: (ids) =>
    request('/threads/reorder', { method: 'POST', body: JSON.stringify({ ids }) }),

  addTask: (threadId, datos) =>
    request(`/threads/${threadId}/tasks`, {
      method: 'POST',
      // Acepta un texto suelto (alta rápida) o el objeto completo del detalle.
      body: JSON.stringify(typeof datos === 'string' ? { text: datos } : datos),
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

  taskHistory: (desde, hasta) =>
    request(`/threads/history?desde=${desde}&hasta=${hasta}`),

  chat: (messages) =>
    request('/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ messages }),
    }),
}
