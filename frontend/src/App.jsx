import { useCallback, useEffect, useState } from 'react'

import { api, UnauthorizedError } from './api.js'
import AgentPanel from './components/AgentPanel.jsx'
import CategoryManager from './components/CategoryManager.jsx'
import Login from './components/Login.jsx'
import TicketGrid from './components/TicketGrid.jsx'
import TicketModal from './components/TicketModal.jsx'
import Toast from './components/Toast.jsx'

// Archivar de un clic no puede pedir que escribas nada, pero la regla de
// negocio exige constancia. Esta es la constancia mínima honesta: dice de dónde
// vino. Para dejar el detalle real está el campo del modal.
const RESOLUCION_RAPIDA = 'Archivado desde la bandeja'

export default function App() {
  // null mientras se comprueba la sesión: evita el parpadeo del login antes de
  // saber si ya hay una cookie válida.
  const [authenticated, setAuthenticated] = useState(null)

  const [categories, setCategories] = useState([])
  const [activeCategory, setActiveCategory] = useState(null)

  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [draftSearch, setDraftSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  const [selected, setSelected] = useState(null)
  const [archivingId, setArchivingId] = useState(null)
  // Lo recién archivado, para poder deshacerlo sin ir a buscarlo entre los
  // archivados. Archivar de un clic solo es cómodo si equivocarse es barato.
  const [ultimoArchivado, setUltimoArchivado] = useState(null)
  const [agentOpen, setAgentOpen] = useState(false)
  const [managingCategories, setManagingCategories] = useState(false)

  useEffect(() => {
    api
      .me()
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false))
  }, [])

  // La búsqueda se envía con retardo: sin esto, cada tecla dispara una
  // petición y la grilla parpadea mientras se escribe.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(draftSearch), 300)
    return () => clearTimeout(timer)
  }, [draftSearch])

  const loadCategories = useCallback(async () => {
    try {
      const lista = await api.categories()
      setCategories(lista)
      // La primera vez se entra por la bandeja, que es donde llega todo.
      setActiveCategory((actual) => {
        if (actual && lista.some((c) => c.id === actual)) return actual
        const bandeja = lista.find((c) => c.is_default) ?? lista[0]
        return bandeja?.id ?? null
      })
    } catch (err) {
      if (err instanceof UnauthorizedError) setAuthenticated(false)
    }
  }, [])

  const loadTickets = useCallback(async () => {
    if (!activeCategory) return
    setLoading(true)
    setError('')
    try {
      const page = await api.tickets({
        categoryId: activeCategory,
        search,
        includeArchived: showArchived,
      })
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
  }, [activeCategory, search, showArchived])

  useEffect(() => {
    if (authenticated) loadCategories()
  }, [authenticated, loadCategories])

  useEffect(() => {
    if (authenticated) loadTickets()
  }, [authenticated, loadTickets])

  async function refrescar() {
    await Promise.all([loadCategories(), loadTickets()])
  }

  async function archivar(ticket) {
    setArchivingId(ticket.id)
    try {
      await api.archiveTicket(ticket.id, RESOLUCION_RAPIDA)
      // Se quita de la lista al tiro en vez de esperar la recarga: el clic
      // tiene que sentirse inmediato.
      setTickets((actuales) => actuales.filter((t) => t.id !== ticket.id))
      setUltimoArchivado({
        ticket,
        estadoPrevio: ticket.status,
        resolucionPrevia: ticket.resolution,
      })
      loadCategories()
    } catch (err) {
      if (err instanceof UnauthorizedError) setAuthenticated(false)
      else setError(err.message)
    } finally {
      setArchivingId(null)
    }
  }

  async function deshacerArchivado() {
    if (!ultimoArchivado) return
    const { ticket, estadoPrevio, resolucionPrevia } = ultimoArchivado
    setUltimoArchivado(null)
    try {
      await api.updateTicket(ticket.id, {
        status: estadoPrevio,
        resolution: resolucionPrevia ?? null,
      })
      await refrescar()
    } catch (err) {
      setError(err.message)
    }
  }

  async function logout() {
    await api.logout().catch(() => {})
    setAuthenticated(false)
    setTickets([])
    setCategories([])
  }

  if (authenticated === null) return <div className="cargando">Cargando…</div>
  if (!authenticated) return <Login onSuccess={() => setAuthenticated(true)} />

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          Si<span>lu</span>
        </span>

        <nav className="cats">
          {categories.map((categoria) => (
            <button
              key={categoria.id}
              aria-pressed={activeCategory === categoria.id}
              onClick={() => setActiveCategory(categoria.id)}
            >
              {categoria.name}
              {categoria.open_count > 0 && (
                <span className="count">{categoria.open_count}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="acciones">
          <button
            className="ghost"
            onClick={() => setManagingCategories(true)}
            title="Gestionar líneas de vida"
          >
            ⚙
          </button>
          <button className="ghost" onClick={logout}>
            Salir
          </button>
        </div>
      </header>

      <main className={`board ${agentOpen ? 'con-agente' : ''}`}>
        <section className="tickets-pane">
          <div className="barra-filtros">
            <div className="buscador">
              <input
                type="search"
                value={draftSearch}
                onChange={(e) => setDraftSearch(e.target.value)}
                placeholder="Buscar en esta categoría"
              />
            </div>
            <label className="toggle-archivados">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => setShowArchived(e.target.checked)}
                style={{ width: 'auto' }}
              />
              Ver archivados
            </label>
          </div>

          <TicketGrid
            tickets={tickets}
            loading={loading}
            error={error}
            onOpen={setSelected}
            onArchive={archivar}
            archivingId={archivingId}
          />
        </section>

        {agentOpen && (
          <AgentPanel
            onChanged={refrescar}
            onClose={() => setAgentOpen(false)}
            onUnauthorized={() => setAuthenticated(false)}
          />
        )}
      </main>

      {!agentOpen && (
        <button
          className="fab"
          onClick={() => setAgentOpen(true)}
          aria-label="Abrir agente"
          title="Agente"
        >
          ✦
        </button>
      )}

      {ultimoArchivado && (
        <Toast
          texto={`Archivado: ${ultimoArchivado.ticket.title}`}
          onDeshacer={deshacerArchivado}
          onCerrar={() => setUltimoArchivado(null)}
        />
      )}

      {selected && (
        <TicketModal
          ticket={selected}
          onClose={() => setSelected(null)}
          onArchivado={async () => {
            setSelected(null)
            await refrescar()
          }}
          onError={setError}
        />
      )}

      {managingCategories && (
        <CategoryManager
          categories={categories}
          onClose={() => setManagingCategories(false)}
          onChanged={refrescar}
        />
      )}
    </div>
  )
}
