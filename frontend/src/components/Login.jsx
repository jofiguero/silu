import { useState } from 'react'

import { api } from '../api.js'
import Logo from './Logo.jsx'

export default function Login({ onSuccess }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const sesion = await api.login(email.trim(), password)
      onSuccess(sesion)
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
          <Logo size={30} />
          <span className="brand-texto">
            Si<span>lu</span>
          </span>
        </h1>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Correo"
          autoFocus
          autoComplete="username"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Contraseña"
          // Le dice al gestor de contraseñas que esto es un inicio de sesión.
          autoComplete="current-password"
        />
        {error && <p className="error">{error}</p>}
        <button className="primary" type="submit" disabled={busy || !email.trim() || !password}>
          {busy ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
