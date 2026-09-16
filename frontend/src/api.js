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

  tickets: ({ status, search } = {}) => {
    const params = new URLSearchParams({ limit: '100' })
    if (status) params.set('status', status)
    if (search) params.set('search', search)
    return request(`/tickets?${params}`)
  },

  chat: (messages) =>
    request('/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ messages }),
    }),
}
