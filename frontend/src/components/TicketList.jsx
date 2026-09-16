import { useEffect, useState } from 'react'

const FILTERS = [
  { value: null, label: 'Todos' },
  { value: 'pendiente', label: 'Pendientes' },
  { value: 'en_curso', label: 'En curso' },
  { value: 'archivado', label: 'Archivados' },
]

const STATUS_LABEL = {
  pendiente: 'pendiente',
  en_curso: 'en curso',
  archivado: 'archivado',
}

function formatDate(iso) {
  return new Date(iso).toLocaleString('es-CL', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function Ticket({ ticket }) {
  return (
    <article className="ticket">
      <h3>{ticket.title}</h3>
      <p>{ticket.summary}</p>

      <div className="meta">
        <span className={`badge ${ticket.status}`}>
          {STATUS_LABEL[ticket.status]}
        </span>
        <span>{formatDate(ticket.created_at)}</span>
      </div>

      {ticket.resolution && (
        <div className="resolution">{ticket.resolution}</div>
      )}

      {/* La transcripción original es secundaria: el summary es lo que se lee.
          Queda a un clic para cuando el resumen no baste. */}
      <details className="raw">
        <summary>Ver original</summary>
        <p>{ticket.raw_text}</p>
      </details>
    </article>
  )
}

export default function TicketList({ tickets, loading, error, filter, onFilter, search, onSearch }) {
  const [draft, setDraft] = useState(search)

  // La búsqueda se envía con retardo: sin esto, cada tecla dispara una
  // petición y la lista parpadea mientras se escribe.
  useEffect(() => {
    const timer = setTimeout(() => onSearch(draft), 300)
    return () => clearTimeout(timer)
  }, [draft, onSearch])

  return (
    <>
      <div className="filters">
        {FILTERS.map(({ value, label }) => (
          <button
            key={label}
            aria-pressed={filter === value}
            onClick={() => onFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="search">
        <input
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Buscar en títulos y descripciones"
        />
      </div>

      <div className="list">
        {error && <p className="empty">{error}</p>}
        {loading && tickets.length === 0 && <p className="loading">Cargando…</p>}
        {!loading && !error && tickets.length === 0 && (
          <p className="empty">
            No hay tickets aquí. Mándale un audio al bot de Telegram.
          </p>
        )}
        {tickets.map((ticket) => (
          <Ticket key={ticket.id} ticket={ticket} />
        ))}
      </div>
    </>
  )
}
