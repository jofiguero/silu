import { useCallback, useEffect, useState } from 'react'

import { api, UnauthorizedError } from './api.js'
import AgentPanel from './components/AgentPanel.jsx'
import Login from './components/Login.jsx'
import TicketList from './components/TicketList.jsx'

export default function App() {
  // null mientras se comprueba la sesión: evita el parpadeo del login antes de
  // saber si ya hay una cookie válida.
  const [authenticated, setAuthenticated] = useState(null)

  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState(null)
  const [search, setSearch] = useState('')

  // En celular solo cabe un panel a la vez; en escritorio se ven ambos y esto
  // se ignora.
  const [tab, setTab] = useState('bandeja')

  useEffect(() => {
    api
      .me()
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
  }, [])

  const loadTickets = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const page = await api.tickets({ status: filter, search })
      setTickets(page.items)
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        setAuthenticated(false)
        return
      }
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filter, search])

  useEffect(() => {
    if (authenticated) loadTickets()
  }, [authenticated, loadTickets])

  async function logout() {
    await api.logout().catch(() => {})
    setAuthenticated(false)
    setTickets([])
  }

  if (authenticated === null) return <div className="loading">Cargando…</div>
  if (!authenticated) return <Login onSuccess={() => setAuthenticated(true)} />

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          Si<span>lu</span>
        </span>
        <button onClick={logout}>Salir</button>
      </header>

      <nav className="tabs">
        <button
          aria-pressed={tab === 'bandeja'}
          onClick={() => setTab('bandeja')}
        >
          Bandeja
        </button>
        <button aria-pressed={tab === 'agente'} onClick={() => setTab('agente')}>
          Agente
        </button>
      </nav>

      <main className="panes">
        <section className={`pane ${tab === 'bandeja' ? 'active' : ''}`}>
          <TicketList
            tickets={tickets}
            loading={loading}
            error={error}
            filter={filter}
            onFilter={setFilter}
            search={search}
            onSearch={setSearch}
          />
        </section>

        <section className={`pane ${tab === 'agente' ? 'active' : ''}`}>
          <AgentPanel
            onChanged={loadTickets}
            onUnauthorized={() => setAuthenticated(false)}
          />
        </section>
      </main>
    </div>
  )
}
