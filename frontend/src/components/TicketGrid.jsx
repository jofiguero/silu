const STATUS_LABEL = {
  pendiente: 'pendiente',
  en_curso: 'en curso',
  archivado: 'archivado',
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString('es-CL', {
    day: '2-digit',
    month: 'short',
  })
}

function Card({ ticket, onOpen }) {
  return (
    <button
      className={`card ${ticket.urgent ? 'urgente' : ''}`}
      onClick={() => onOpen(ticket)}
    >
      <h3>{ticket.title}</h3>
      <p>{ticket.summary}</p>
      <div className="meta">
        {ticket.urgent && <span className="badge urgente">urgente</span>}
        <span className={`badge ${ticket.status}`}>
          {STATUS_LABEL[ticket.status]}
        </span>
        <span>{formatDate(ticket.created_at)}</span>
      </div>
    </button>
  )
}

export default function TicketGrid({ tickets, loading, error, onOpen }) {
  if (error) return <p className="vacio">{error}</p>
  if (loading && tickets.length === 0) return <p className="cargando">Cargando…</p>
  if (tickets.length === 0) {
    return (
      <p className="vacio">
        No hay tickets en esta categoría. Mándale un audio al bot de Telegram.
      </p>
    )
  }

  return (
    <div className="tickets-grid">
      {tickets.map((ticket) => (
        <Card key={ticket.id} ticket={ticket} onOpen={onOpen} />
      ))}
    </div>
  )
}
