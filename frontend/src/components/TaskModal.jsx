import { useEffect, useRef, useState } from 'react'

function formatFull(iso) {
  return new Date(iso).toLocaleString('es-CL', {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Detalle de una tarea, que sirve también para crearla.
 *
 * Es el mismo formulario en los dos casos: crear una tarea con descripción y
 * editarla después son la misma operación desde el punto de vista de quien
 * escribe, y tener dos pantallas distintas para eso sería repetir el trabajo.
 */
export default function TaskModal({ task, thread, onGuardar, onCrear, onClose, onError }) {
  const creando = !task

  const [texto, setTexto] = useState(task?.text ?? '')
  const [descripcion, setDescripcion] = useState(task?.description ?? '')
  const [busy, setBusy] = useState(false)
  const textoRef = useRef(null)

  const sucio =
    texto !== (task?.text ?? '') || descripcion !== (task?.description ?? '')

  useEffect(() => {
    function onKey(event) {
      // Escape cierra solo si no hay cambios sin guardar: si no, se perderían
      // sin aviso.
      if (event.key === 'Escape' && !sucio) onClose()
      // Ctrl/Cmd+Enter guarda sin sacar las manos del teclado.
      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) guardar()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  async function guardar() {
    const limpio = texto.trim()
    if (!limpio) {
      textoRef.current?.focus()
      return
    }

    setBusy(true)
    try {
      if (creando) {
        await onCrear(thread, { text: limpio, description: descripcion.trim() || null })
      } else {
        await onGuardar(task, {
          text: limpio,
          description: descripcion.trim() || null,
        })
      }
      onClose()
    } catch (err) {
      onError(err.message)
      setBusy(false)
    }
  }

  return (
    <div
      className="overlay"
      onClick={sucio ? undefined : onClose}
      role="presentation"
    >
      <div
        className="modal tarea-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={creando ? 'Nueva tarea' : task.text}
      >
        <div className="modal-head">
          <span className={`pastilla color-${thread.color}`}>{thread.name}</span>
          <span style={{ flex: 1 }} />
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="campos">
          <div className="campo">
            <dt>Tarea</dt>
            <dd>
              <input
                ref={textoRef}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder="Qué hay que hacer"
                autoFocus
                maxLength={300}
              />
            </dd>
          </div>

          <div className="campo">
            <dt>Descripción</dt>
            <dd>
              <textarea
                className="tarea-descripcion"
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                placeholder="El detalle que no cabe en el papel: contexto, enlaces, lo que haya que recordar al retomarla."
                maxLength={5000}
              />
            </dd>
          </div>

          {!creando && (
            <>
              <div className="campo">
                <dt>Estado</dt>
                <dd>
                  <span className={`badge ${task.done ? 'archivado' : 'pendiente'}`}>
                    {task.done ? 'hecha' : 'pendiente'}
                  </span>
                  {task.active && !task.done && (
                    <>
                      {' '}
                      <span className="badge urgente">en curso ahora</span>
                    </>
                  )}
                </dd>
              </div>

              <div className="campo">
                <dt>Creada</dt>
                <dd>{formatFull(task.created_at)}</dd>
              </div>

              {task.done_at && (
                <div className="campo">
                  <dt>Terminada</dt>
                  <dd>{formatFull(task.done_at)}</dd>
                </div>
              )}
            </>
          )}

          <div className="acciones-modal">
            <span style={{ flex: 1 }} />
            <button onClick={onClose} disabled={busy}>
              {sucio ? 'Descartar' : 'Cerrar'}
            </button>
            <button
              className="primary"
              onClick={guardar}
              disabled={busy || !texto.trim() || (!creando && !sucio)}
            >
              {busy ? 'Guardando…' : creando ? 'Crear' : 'Guardar'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
