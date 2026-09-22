import { useEffect, useState } from 'react'

import { api } from '../api.js'
import { useCierreExterior } from '../cierre.js'

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

export default function TicketModal({
  ticket,
  onClose,
  onArchivado,
  onRegistrarGasto,
  onError,
}) {
  const [resolucion, setResolucion] = useState('')
  const [busy, setBusy] = useState(false)

  // Escape cierra: es el reflejo de cualquiera frente a un modal.
  useEffect(() => {
    function onKey(event) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!ticket) return null

  const archivado = ticket.status === 'archivado'

  async function archivar() {
    setBusy(true)
    try {
      // El texto escrito manda; si está vacío, al menos queda constancia de
      // que se archivó desde aquí.
      await api.archiveTicket(
        ticket.id,
        resolucion.trim() || 'Archivado desde el detalle',
      )
      await onArchivado()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    // Clic deliberado fuera cierra. El gesto tiene que empezar y terminar en
    // el fondo: subrayar texto del modal y soltar afuera no cierra.
    <div className="overlay" {...useCierreExterior(onClose)}>
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

        {!archivado && (
          <div className="acciones-modal">
            <input
              value={resolucion}
              onChange={(e) => setResolucion(e.target.value)}
              placeholder="¿Qué hiciste con esto? (opcional)"
              onKeyDown={(e) => {
                if (e.key === 'Enter') archivar()
              }}
            />
            <button
              onClick={onRegistrarGasto}
              disabled={busy}
              title="Abre el formulario de gastos con esta descripción"
            >
              Registrar como gasto
            </button>
            <button className="primary" onClick={archivar} disabled={busy}>
              {busy ? 'Archivando…' : '✓ Archivar'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
