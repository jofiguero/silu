import { useCallback, useEffect, useState } from 'react'

import { api } from '../api.js'
import { useCierreExterior } from '../cierre.js'
import { hoyIso, iso } from '../semana.js'

const ETIQUETAS = {
  creada: 'creada',
  hecha: 'hecha',
  reabierta: 'reabierta',
  movida: 'movida',
  eliminada: 'eliminada',
}

function fecha(isoTexto) {
  return new Date(isoTexto).toLocaleString('es-CL', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function diaCorto(valor) {
  if (!valor) return 'sin día'
  const [, m, d] = valor.split('-')
  return `${d}/${m}`
}

/** Días atrás desde hoy, como 'YYYY-MM-DD'. */
function hace(dias) {
  const f = new Date()
  f.setDate(f.getDate() - dias)
  return iso(f)
}

/**
 * Qué pasó con las tareas entre dos fechas.
 *
 * Lee el registro de eventos, no la tabla de tareas: ahí está lo que la tabla
 * no puede guardar —los cierres que después se reabrieron, de qué día venía
 * algo que se pospuso, y las tareas que se borraron.
 */
export default function TaskHistory({ onClose, onError }) {
  const [desde, setDesde] = useState(() => hace(30))
  const [hasta, setHasta] = useState(hoyIso())
  const [datos, setDatos] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [filtro, setFiltro] = useState('hecha')

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setDatos(await api.taskHistory(desde, hasta))
    } catch (err) {
      onError(err.message)
    } finally {
      setCargando(false)
    }
  }, [desde, hasta, onError])

  useEffect(() => {
    cargar()
  }, [cargar])

  const eventos = (datos?.eventos ?? []).filter(
    (e) => filtro === 'todo' || e.kind === filtro,
  )

  return (
    <div className="overlay" {...useCierreExterior(onClose)}>
      <div
        className="modal historico"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Histórico de tareas"
      >
        <div className="modal-head">
          <h2>Histórico</h2>
          <span style={{ flex: 1 }} />
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="historico-rango">
          <label>
            Desde
            <input
              type="date"
              value={desde}
              max={hasta}
              onChange={(e) => e.target.value && setDesde(e.target.value)}
            />
          </label>
          <label>
            Hasta
            <input
              type="date"
              value={hasta}
              min={desde}
              onChange={(e) => e.target.value && setHasta(e.target.value)}
            />
          </label>
          <div className="atajos">
            <button onClick={() => { setDesde(hace(6)); setHasta(hoyIso()) }}>
              7 días
            </button>
            <button onClick={() => { setDesde(hace(29)); setHasta(hoyIso()) }}>
              30 días
            </button>
            <button onClick={() => { setDesde(hace(89)); setHasta(hoyIso()) }}>
              90 días
            </button>
          </div>
        </div>

        {cargando && !datos ? (
          <p className="cargando">Cargando…</p>
        ) : (
          datos && (
            <>
              <div className="historico-resumen">
                <div className="cifra">
                  <strong>{datos.hechas}</strong>
                  <span>cerradas</span>
                </div>
                <div className="cifra">
                  <strong>{datos.creadas}</strong>
                  <span>creadas</span>
                </div>
                <div className="cifra">
                  <strong>{datos.movidas}</strong>
                  <span>pospuestas</span>
                </div>
                <div className="cifra">
                  <strong>{datos.eliminadas}</strong>
                  <span>eliminadas</span>
                </div>
                <div className="cifra">
                  <strong>
                    {datos.atraso_promedio === null
                      ? '—'
                      : `${datos.atraso_promedio}d`}
                  </strong>
                  <span>atraso medio</span>
                </div>
                <div className="cifra">
                  <strong>
                    {datos.a_tiempo}/{datos.a_tiempo + datos.atrasadas || 0}
                  </strong>
                  <span>a tiempo</span>
                </div>
              </div>

              {datos.atraso_promedio === null && datos.hechas > 0 && (
                <p className="nota">
                  Nada de lo cerrado en este rango tenía día asignado, así que
                  no hay atraso que medir. Bajar tareas a un día en el
                  planificador es lo que hace que esta cifra signifique algo.
                </p>
              )}

              <div className="historico-filtros">
                {['hecha', 'movida', 'creada', 'eliminada', 'todo'].map((k) => (
                  <button
                    key={k}
                    aria-pressed={filtro === k}
                    onClick={() => setFiltro(k)}
                  >
                    {k === 'todo' ? 'Todo' : ETIQUETAS[k]}
                  </button>
                ))}
              </div>

              {eventos.length === 0 ? (
                <p className="vacio">Nada en este rango.</p>
              ) : (
                <ul className="historico-lista">
                  {eventos.map((e) => (
                    <li key={e.id} className={`evento ${e.kind}`}>
                      <span className="evento-cuando">{fecha(e.at)}</span>
                      <span className="evento-thread">{e.thread_name}</span>
                      <span className="evento-texto">{e.task_text}</span>
                      {e.kind === 'movida' && (
                        <span className="evento-dato">
                          {diaCorto(e.from_day)} → {diaCorto(e.to_day)}
                        </span>
                      )}
                      {e.kind === 'hecha' && e.atraso !== null && (
                        <span
                          className={`evento-dato ${e.atraso > 0 ? 'tarde' : 'puntual'}`}
                        >
                          {e.atraso > 0
                            ? `${e.atraso}d tarde`
                            : e.atraso < 0
                              ? `${-e.atraso}d antes`
                              : 'a tiempo'}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )
        )}
      </div>
    </div>
  )
}
