import { useState } from 'react'

import { api } from '../api.js'

export default function Login({ onSuccess }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(password)
      onSuccess()
    } catch (err) {
      setError(err.message)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <h1>
          Si<span>lu</span>
        </h1>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Contraseña"
          autoFocus
          // Le dice al gestor de contraseñas que esto es un inicio de sesión.
          autoComplete="current-password"
        />
        {error && <p className="error">{error}</p>}
        <button className="primary" type="submit" disabled={busy || !password}>
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
