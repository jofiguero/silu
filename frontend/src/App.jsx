import { useCallback, useEffect, useState } from 'react'

import { api, UnauthorizedError } from './api.js'
import { useRefrescoPeriodico } from './refresco.js'
import { VENTANAS, useVentana } from './ruta.js'
import AccountModal from './components/AccountModal.jsx'
import AgentPanel from './components/AgentPanel.jsx'
import Dashboard from './components/Dashboard.jsx'
import Expenses from './components/Expenses.jsx'
import Login from './components/Login.jsx'
import Logo from './components/Logo.jsx'
import Prompts from './components/Prompts.jsx'
import TicketGrid from './components/TicketGrid.jsx'
import TicketModal from './components/TicketModal.jsx'
import Toast from './components/Toast.jsx'

// Archivar de un clic no puede pedir que escribas nada, pero la regla de
// negocio exige constancia. Esta es la constancia mínima honesta: dice de dónde
// vino. Para dejar el detalle real está el campo del modal.
const RESOLUCION_RAPIDA = 'Archivado desde la bandeja'

const ETIQUETAS = {
  bandeja: 'Bandeja',
  tareas: 'Tareas',
  gastos: 'Gastos',
  prompts: 'Prompts',
}

export default function App() {
  // null mientras se comprueba la sesión: evita el parpadeo del login antes de
  // saber si ya hay una cookie válida.
  const [authenticated, setAuthenticated] = useState(null)
  // Quién entró. Se muestra en la barra: con varias cuentas, saber en cuál
  // estás deja de ser obvio.
  const [sesion, setSesion] = useState(null)

  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [draftSearch, setDraftSearch] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  const [selected, setSelected] = useState(null)
  const [busyId, setBusyId] = useState(null)
  // Aviso con acción de deshacer: equivocarse tiene que costar un clic, no una
  // búsqueda entre los archivados.
  const [aviso, setAviso] = useState(null)

  // Cuatro espacios del mismo sistema: bandeja, tareas, gastos y prompts.
  // Viven en la URL, así que recargar deja donde estabas y cada ventana se
  // puede enlazar o dejar abierta en una pestaña.
  const [vista, setVista] = useVentana()
  // Descripción que viaja de un ticket al formulario de gastos. El monto NO
  // viaja: lo escribe la persona, para que un número del LLM nunca entre solo
  // a la base de gastos.
  const [borradorGasto, setBorradorGasto] = useState(null)
  const [agentOpen, setAgentOpen] = useState(false)
  const [verCuenta, setVerCuenta] = useState(false)

  useEffect(() => {
    api
      .me()
      .then((datos) => {
        setSesion(datos)
        setAuthenticated(true)
      })
      .catch(() => setAuthenticated(false))
  }, [])

  // La búsqueda se envía con retardo: sin esto, cada tecla dispara una
  // petición y la grilla parpadea mientras se escribe.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(draftSearch), 300)
    return () => clearTimeout(timer)
  }, [draftSearch])

  const loadTickets = useCallback(async ({ silencioso = false } = {}) => {
    // El refresco automático no enciende el cargando: un parpadeo de la
    // grilla cada veinte segundos sería peor que no actualizar.
    if (!silencioso) {
      setLoading(true)
      setError('')
    }
    try {
      const page = await api.tickets({ search, includeArchived: showArchived })
      setTickets(page.items)
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        setAuthenticated(false)
        return
      }
      // Un fallo del refresco automático no se muestra: la red se cae un
      // segundo y no hay nada que la persona pueda hacer con ese aviso.
      if (!silencioso) setError(err.message)
    } finally {
      if (!silencioso) setLoading(false)
    }
  }, [search, showArchived])

  useEffect(() => {
    if (authenticated && vista === 'bandeja') loadTickets()
  }, [authenticated, vista, loadTickets])

  // La bandeja recibe capturas del bot mientras está abierta. Se suspende con
  // un ticket abierto: recargar la lista debajo del modal no aporta nada.
  const refrescarBandeja = useCallback(
    () => loadTickets({ silencioso: true }),
    [loadTickets],
  )
  useRefrescoPeriodico(refrescarBandeja, {
    activo: authenticated === true && vista === 'bandeja' && !selected,
  })

  /** Ejecuta una acción sobre un ticket y deja un aviso con cómo revertirla. */
  async function operar(ticket, { accion, texto, revertir }) {
    setBusyId(ticket.id)
    try {
      await accion()
      // Se quita de la lista al tiro en vez de esperar la recarga: la acción
      // tiene que sentirse inmediata.
      setTickets((actuales) => actuales.filter((t) => t.id !== ticket.id))
      setAviso({
        texto,
        deshacer: async () => {
          await revertir()
          await loadTickets()
        },
      })
    } catch (err) {
      if (err instanceof UnauthorizedError) setAuthenticated(false)
      else setError(err.message)
      // Si falló, la lista puede haber quedado desfasada.
      loadTickets()
    } finally {
      setBusyId(null)
    }
  }

  function archivar(ticket) {
    return operar(ticket, {
      accion: () => api.archiveTicket(ticket.id, RESOLUCION_RAPIDA),
      texto: `Archivado: ${ticket.title}`,
      revertir: () =>
        api.updateTicket(ticket.id, {
          status: ticket.status,
          resolution: ticket.resolution ?? null,
        }),
    })
  }

  async function logout() {
    await api.logout().catch(() => {})
    setAuthenticated(false)
    setSesion(null)
    setTickets([])
  }

  if (authenticated === null) return <div className="cargando">Cargando…</div>
  if (!authenticated)
    return (
      <Login
        onSuccess={(datos) => {
          setSesion(datos)
          setAuthenticated(true)
        }}
      />
    )

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">
          <Logo size={22} />
          <span className="brand-texto">
            Si<span>lu</span>
          </span>
        </span>

        <nav className="vistas">
          {VENTANAS.map((v) => (
            <a
              key={v}
              href={`/${v}`}
              aria-current={vista === v ? 'page' : undefined}
              onClick={(e) => {
                // Ctrl, cmd o el botón del medio abren en otra pestaña: eso lo
                // resuelve el navegador y no hay que interceptarlo.
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return
                e.preventDefault()
                setVista(v)
              }}
            >
              {ETIQUETAS[v]}
            </a>
          ))}
        </nav>

        <span className="relleno" />

        <div className="acciones">
          {sesion?.email && (
            <button
              className="quien"
              onClick={() => setVerCuenta(true)}
              title="Tu cuenta y el vínculo con Telegram"
            >
              {sesion.email}
              {sesion.role === 'admin' && <span className="badge">admin</span>}
              {!sesion.telegram_vinculado && (
                <span className="badge pendiente" title="Telegram sin vincular">
                  ⚠
                </span>
              )}
            </button>
          )}
          <button className="ghost" onClick={logout}>
            Salir
          </button>
        </div>
      </header>

      {vista === 'tareas' ? (
        <Dashboard
          onUnauthorized={() => setAuthenticated(false)}
          onError={setError}
        />
      ) : vista === 'prompts' ? (
        <Prompts
          onUnauthorized={() => setAuthenticated(false)}
          onError={setError}
        />
      ) : vista === 'gastos' ? (
        <Expenses
          onUnauthorized={() => setAuthenticated(false)}
          onError={setError}
          borrador={borradorGasto}
          onBorradorUsado={() => setBorradorGasto(null)}
        />
      ) : (
        <main className={`board ${agentOpen ? 'con-agente' : ''}`}>
          <section className="tickets-pane">
            <div className="barra-filtros">
              <div className="buscador">
                <input
                  type="search"
                  value={draftSearch}
                  onChange={(e) => setDraftSearch(e.target.value)}
                  placeholder="Buscar en la bandeja"
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
              busyId={busyId}
            />
          </section>

          {agentOpen && (
            <AgentPanel
              onChanged={loadTickets}
              onClose={() => setAgentOpen(false)}
              onUnauthorized={() => setAuthenticated(false)}
            />
          )}
        </main>
      )}

      {vista === 'bandeja' && !agentOpen && (
        <button
          className="fab"
          onClick={() => setAgentOpen(true)}
          aria-label="Abrir agente"
          title="Agente"
        >
          ✦
        </button>
      )}

      {vista !== 'bandeja' && error && (
        <Toast texto={error} onDeshacer={null} onCerrar={() => setError('')} />
      )}

      {aviso && (
        <Toast
          texto={aviso.texto}
          onDeshacer={async () => {
            const { deshacer } = aviso
            setAviso(null)
            try {
              await deshacer()
            } catch (err) {
              setError(err.message)
            }
          }}
          onCerrar={() => setAviso(null)}
        />
      )}

      {verCuenta && sesion && (
        <AccountModal
          sesion={sesion}
          onClose={() => setVerCuenta(false)}
          onCambio={setSesion}
          onError={setError}
        />
      )}

      {selected && (
        <TicketModal
          ticket={selected}
          onClose={() => setSelected(null)}
          onRegistrarGasto={async () => {
            // Solo viaja la descripción; el monto lo escribe la persona.
            setBorradorGasto(selected.summary)
            setSelected(null)
            setVista('gastos')
            await archivar(selected)
          }}
          onArchivado={async () => {
            setSelected(null)
            await loadTickets()
          }}
          onError={setError}
        />
      )}
    </div>
  )
}
