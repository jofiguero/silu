import { useCallback, useEffect, useState } from 'react'

import { api } from '../api.js'
import {
  etiquetaSemana,
  etiquetaSemanaCorta,
  semanaActual,
  sumarSemanas,
} from '../semana.js'
import { useCierreExterior } from '../cierre.js'

// Dos meses hacia adelante. Más lejos que eso no es un compromiso, es
// "algún día", y para eso ya está este mismo cajón.
const SEMANAS_ELEGIBLES = 8

/**
 * "Otras tareas" de un thread: lo que hay que hacer, pero no esta semana.
 *
 * Antes esto no tenía dónde vivir. O ensuciaba el pizarrón —y el pizarrón
 * solo sirve si lo que está ahí es lo que hay que mover sí o sí— o se iba a la
 * Bandeja a perderse entre capturas sin procesar.
 */
export default function BacklogDrawer({ thread, onClose, onChanged, onError }) {
  const [tareas, setTareas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [nueva, setNueva] = useState('')
  const [busy, setBusy] = useState(false)
  // Un solo destino para todo el cajón y no uno por tarea: lo normal es
  // repartir varias a la misma semana, y un selector por fila sería ruido.
  const [destino, setDestino] = useState(semanaActual())
  const semanasElegibles = Array.from({ length: SEMANAS_ELEGIBLES }, (_, i) =>
    sumarSemanas(semanaActual(), i),
  )

  const cargar = useCallback(async () => {
    try {
      const hilos = await api.threads({ scope: 'backlog' })
      const mio = hilos.find((h) => h.id === thread.id)
      setTareas(mio?.tasks ?? [])
    } catch (err) {
      onError(err.message)
    } finally {
      setCargando(false)
    }
  }, [thread.id, onError])

  useEffect(() => {
    cargar()
  }, [cargar])

  async function ejecutar(accion) {
    setBusy(true)
    try {
      await accion()
      await cargar()
      // El pizarrón también cambia: traer una tarea a la semana la hace
      // aparecer detrás de este panel.
      await onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" {...useCierreExterior(onClose)}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Otras tareas de ${thread.name}`}
      >
        <div className="modal-head">
          <span className={`pastilla color-${thread.color}`}>{thread.name}</span>
          <h2>Otras tareas</h2>
          <span style={{ flex: 1 }} />
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="campos">
          <p className="nota">
            Lo que hay que hacer en este thread pero que no alcanza esta semana.
            Tráelo cuando corresponda.
          </p>

          {tareas.length > 0 && (
            <label className="backlog-destino">
              Comprometer para
              <select value={destino} onChange={(e) => setDestino(e.target.value)}>
                {semanasElegibles.map((lunes) => (
                  <option key={lunes} value={lunes}>
                    {etiquetaSemanaCorta(lunes)}
                  </option>
                ))}
              </select>
            </label>
          )}

          {cargando ? (
            <p className="cargando">Cargando…</p>
          ) : tareas.length === 0 ? (
            <p className="vacio">Nada guardado para después.</p>
          ) : (
            <ul className="backlog">
              {tareas.map((t) => (
                <li key={t.id}>
                  <div className="backlog-texto">
                    <span>{t.text}</span>
                    {t.description && <p className="nota">{t.description}</p>}
                  </div>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() =>
                      ejecutar(() =>
                        api.updateTask(t.id, { week: destino, day: null }),
                      )
                    }
                    title={`Comprometerla para ${etiquetaSemana(destino).toLowerCase()}`}
                  >
                    → {etiquetaSemanaCorta(destino)}
                  </button>
                  <button
                    className="danger"
                    disabled={busy}
                    onClick={() => {
                      if (!window.confirm(`¿Eliminar "${t.text}"?`)) return
                      ejecutar(() => api.deleteTask(t.id))
                    }}
                    aria-label={`Eliminar ${t.text}`}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}

          <form
            className="etiqueta-fila"
            onSubmit={(e) => {
              e.preventDefault()
              const texto = nueva.trim()
              if (!texto) return
              ejecutar(async () => {
                await api.addTask(thread.id, { text: texto, backlog: true })
                setNueva('')
              })
            }}
          >
            <input
              value={nueva}
              onChange={(e) => setNueva(e.target.value)}
              placeholder="Algo que hacer más adelante"
              maxLength={300}
            />
            <button disabled={busy || !nueva.trim()}>Agregar</button>
          </form>
        </div>
      </div>
    </div>
  )
}
