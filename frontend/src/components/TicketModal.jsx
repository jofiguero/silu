import { useEffect } from 'react'

const STATUS_LABEL = {
  pendiente: 'pendiente',
  en_curso: 'en curso',
  archivado: 'archivado',
}

function formatFull(iso) {
  return new Date(iso).toLocaleString('es-CL', {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function Campo({ titulo, children }) {
  return (
    <div className="campo">
      <dt>{titulo}</dt>
      <dd>{children}</dd>
    </div>
  )
}

export default function TicketModal({ ticket, onClose }) {
  // Escape cierra: es el reflejo de cualquiera frente a un modal.
  useEffect(() => {
    function onKey(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!ticket) return null

  return (
    <div
      className="overlay"
      // Clic fuera cierra; el stopPropagation de adentro evita que un clic
      // dentro del modal lo cierre por accidente.
      onClick={onClose}
      role="presentation"
    >
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={ticket.title}
      >
        <div className="modal-head">
          <h2>{ticket.title}</h2>
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <dl className="campos">
          <Campo titulo="Descripción">{ticket.summary}</Campo>

          <Campo titulo="Categoría">{ticket.category_name}</Campo>

          <Campo titulo="Estado">
            <span className={`badge ${ticket.status}`}>
              {STATUS_LABEL[ticket.status]}
            </span>
            {ticket.urgent && (
              <>
                {' '}
                <span className="badge urgente">urgente</span>
              </>
            )}
          </Campo>

          {ticket.resolution && (
            <Campo titulo="Resolución">{ticket.resolution}</Campo>
          )}

          <Campo titulo="Creado">{formatFull(ticket.created_at)}</Campo>

          {ticket.updated_at !== ticket.created_at && (
            <Campo titulo="Última modificación">
              {formatFull(ticket.updated_at)}
            </Campo>
          )}

          <div className="campo">
            <dt>Transcripción original</dt>
            <dd className="original">{ticket.raw_text}</dd>
          </div>

          <Campo titulo="Identificador">
            <code>{ticket.id}</code>
          </Campo>
        </dl>
      </div>
    </div>
  )
}
