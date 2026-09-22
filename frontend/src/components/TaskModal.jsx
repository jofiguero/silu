import { useEffect, useRef, useState } from 'react'

import { diasDe, etiquetaDia, hoyIso, semanaActual } from '../semana.js'

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
  // Dónde vive la tarea. Una nueva nace comprometida para esta semana, que es
  // lo que significa escribirla en el pizarrón.
  const areaInicial = task ? (task.week ? (task.day ? 'dia' : 'semana') : 'otras') : 'semana'
  const [area, setArea] = useState(areaInicial)
  const [dia, setDia] = useState(task?.day ?? hoyIso())
  const [busy, setBusy] = useState(false)
  const textoRef = useRef(null)

  const diaInicial = task?.day ?? null
  const sucio =
    texto !== (task?.text ?? '') ||
    descripcion !== (task?.description ?? '') ||
    area !== areaInicial ||
    (area === 'dia' && dia !== diaInicial)

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
        await onCrear(thread, {
          text: limpio,
          description: descripcion.trim() || null,
          // Al crear basta con decir dónde nace: el backend deduce la semana
          // a partir del día.
          ...(area === 'otras' ? { backlog: true } : {}),
          ...(area === 'dia' ? { day: dia } : {}),
        })
      } else {
        await onGuardar(task, {
          text: limpio,
          description: descripcion.trim() || null,
          // Mover entre áreas es escribir una fecha, no copiar la tarea:
          // null en semana la manda a otras tareas, null en día la devuelve a
          // la lista semanal.
          ...(area === 'otras' ? { week: null } : {}),
          ...(area === 'semana' ? { week: task.week ?? semanaActual(), day: null } : {}),
          ...(area === 'dia' ? { day: dia } : {}),
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

          {/* El arrastre es el camino cómodo cuando ya estás dentro del
              thread; esto es el que funciona en el teléfono y el que sirve
              cuando armas el día cruzando varios threads. */}
          <div className="campo">
            <dt>Cuándo</dt>
            <dd>
              <div className="area-tarea">
                <button
                  className={area === 'otras' ? 'elegida' : ''}
                  onClick={() => setArea('otras')}
                  type="button"
                  title="Hay que hacerla en este thread, pero no esta semana"
                >
                  Otras tareas
                </button>
                <button
                  className={area === 'semana' ? 'elegida' : ''}
                  onClick={() => setArea('semana')}
                  type="button"
                >
                  Esta semana
                </button>
                <button
                  className={area === 'dia' ? 'elegida' : ''}
                  onClick={() => setArea('dia')}
                  type="button"
                >
                  Un día
                </button>
              </div>

              {area === 'dia' && (
                <div className="elegir-dia">
                  {/* Acotado a esta semana a propósito: todavía no hay forma
                      de navegar a otra semana en el pizarrón, así que una
                      tarea puesta en la siguiente desaparecería sin vuelta. */}
                  <input
                    type="date"
                    value={dia}
                    min={semanaActual()}
                    max={diasDe(semanaActual())[6].fecha}
                    onChange={(e) => setDia(e.target.value || hoyIso())}
                  />
                  <span className="nota">{etiquetaDia(dia)}</span>
                </div>
              )}
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
