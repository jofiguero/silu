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

function Card({ ticket, onOpen, onArchive, ocupado }) {
  const archivado = ticket.status === 'archivado'

  return (
    // div y no button: un botón dentro de otro botón es HTML inválido, y el
    // archivado rápido necesita su propio control.
    <div
      className={`card ${ticket.urgent ? 'urgente' : ''} ${archivado ? 'ya-archivado' : ''} ${ocupado ? 'ocupado' : ''}`}
      // Arrastrar la tarjeta sobre una categoría de la barra la mueve ahí.
      // Solo funciona con mouse: el arrastre nativo no existe en pantallas
      // táctiles, y para eso está el selector del detalle.
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData('text/plain', ticket.id)
        event.dataTransfer.effectAllowed = 'move'
      }}
      onClick={() => onOpen(ticket)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(ticket)
        }
      }}
      role="button"
      tabIndex={0}
    >
      {!archivado && (
        <button
          className="archivar"
          title="Archivar"
          aria-label={`Archivar ${ticket.title}`}
          disabled={ocupado}
          onClick={(event) => {
            // Sin esto, el clic llegaría a la tarjeta y abriría el detalle.
            event.stopPropagation()
            onArchive(ticket)
          }}
        >
          ✓
        </button>
      )}

      <h3>{ticket.title}</h3>
      <p>{ticket.summary}</p>
      <div className="meta">
        {ticket.urgent && <span className="badge urgente">urgente</span>}
        <span className={`badge ${ticket.status}`}>
          {STATUS_LABEL[ticket.status]}
        </span>
        <span>{formatDate(ticket.created_at)}</span>
      </div>
    </div>
  )
}

export default function TicketGrid({
  tickets,
  loading,
  error,
  onOpen,
  onArchive,
  busyId,
}) {
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
        <Card
          key={ticket.id}
          ticket={ticket}
          onOpen={onOpen}
          onArchive={onArchive}
          ocupado={busyId === ticket.id}
        />
      ))}
    </div>
  )
}
