import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api.js'
import TaskModal from './TaskModal.jsx'
import {
  diasDe,
  etiquetaSemana,
  hoyIso,
  semanaActual,
  sumarSemanas,
} from '../semana.js'

/**
 * Las dos primeras palabras, para las columnas de día.
 *
 * Son siete columnas en el ancho de la pantalla: con el texto completo cada
 * tarea ocupa cuatro líneas y el día deja de leerse de un vistazo. El texto
 * entero sigue estando en el title y en el detalle.
 */
function dosPalabras(texto) {
  const palabras = texto.trim().split(/\s+/)
  return palabras.length <= 2 ? texto : `${palabras.slice(0, 2).join(' ')}…`
}

/** Una tarea arrastrable. El texto abre el detalle; ese es el camino táctil. */
function Chip({ task, resumido, onToggle, onAbrir, onArrastrar }) {
  return (
    <li
      className={`chip ${task.done ? 'hecha' : ''} ${
        task.active && !task.done ? 'en-curso' : ''
      }`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', task.id)
        e.dataTransfer.effectAllowed = 'move'
        onArrastrar(task)
      }}
    >
      <label>
        <input type="checkbox" checked={task.done} onChange={() => onToggle(task)} />
        <span className="caja" aria-hidden="true" />
      </label>
      <button
        className={`chip-texto ${resumido ? 'resumido' : ''}`}
        onClick={() => onAbrir(task)}
        title={resumido ? task.text : 'Abrir detalle'}
      >
        {resumido ? dosPalabras(task.text) : task.text}
        {task.description && <span className="tiene-detalle"> ≡</span>}
      </button>
    </li>
  )
}

/** Una zona donde soltar tareas: la semana, un día, u otras tareas. */
function Zona({
  titulo,
  nota,
  tareas,
  destino,
  encima,
  resumido,
  onEncima,
  onSoltar,
  children,
  ...chip
}) {
  return (
    <section
      className={`zona ${encima === clave(destino) ? 'encima' : ''}`}
      onDragOver={(e) => {
        // Sin preventDefault el navegador no considera esto un destino válido.
        e.preventDefault()
        onEncima(clave(destino))
      }}
      onDrop={(e) => {
        e.preventDefault()
        onSoltar(destino)
      }}
    >
      <header>
        <h4>{titulo}</h4>
        {nota && <span className="zona-nota">{nota}</span>}
        <span className="zona-cuenta">{tareas.length || ''}</span>
      </header>
      <ul className="chips">
        {tareas.map((t) => (
          <Chip key={t.id} task={t} resumido={resumido} {...chip} />
        ))}
      </ul>
      {children}
    </section>
  )
}

/** Identifica un destino con un string: comparar objetos re-renderizaría. */
const clave = (destino) =>
  destino.tipo === 'dia' ? `dia:${destino.dia}` : destino.tipo

/**
 * Planificar un thread: bajar lo de la semana a los días.
 *
 * Arrastrar aquí no copia la tarea a otra lista, le escribe una fecha. Por eso
 * bajarla a un día no la saca de la semana y cerrarla en cualquier parte la
 * cierra en todas: es siempre la misma tarea.
 */
export default function ThreadPlanner({ thread, semanaInicial, onClose, onError }) {
  const [semana, setSemana] = useState(semanaInicial ?? semanaActual())
  const [todas, setTodas] = useState([])
  const [cargando, setCargando] = useState(true)
  const [verOtras, setVerOtras] = useState(false)
  // Pantalla completa dentro de la página: siete columnas de días piden más
  // ancho del que da un modal.
  const [completa, setCompleta] = useState(false)
  const [detalle, setDetalle] = useState(null)
  const [nueva, setNueva] = useState('')
  const [encima, setEncima] = useState(null)
  const arrastrada = useRef(null)

  const cargar = useCallback(async () => {
    try {
      const [deSemana, deOtras] = await Promise.all([
        api.threads({ scope: 'week', week: semana }),
        api.threads({ scope: 'backlog' }),
      ])
      const mias = (lista) => lista.find((h) => h.id === thread.id)?.tasks ?? []
      setTodas([...mias(deSemana), ...mias(deOtras)])
    } catch (err) {
      onError(err.message)
    } finally {
      setCargando(false)
    }
  }, [thread.id, semana, onError])

  useEffect(() => {
    cargar()
  }, [cargar])

  const dias = diasDe(semana)
  const sinBajar = todas.filter((t) => t.week === semana && !t.day)
  const otras = todas.filter((t) => !t.week)
  const delDia = (fecha) => todas.filter((t) => t.day === fecha)

  /** Mover es escribir una fecha, no copiar la tarea a otra lista. */
  async function soltar(destino) {
    const task = arrastrada.current
    arrastrada.current = null
    setEncima(null)
    if (!task) return

    // Ya estaba ahí: no vale la pena una petición.
    const igual =
      (destino.tipo === 'otras' && !task.week) ||
      (destino.tipo === 'semana' && task.week === semana && !task.day) ||
      (destino.tipo === 'dia' && task.day === destino.dia)
    if (igual) return

    const cambios =
      destino.tipo === 'otras'
        ? { week: null }
        : destino.tipo === 'semana'
          ? { week: semana, day: null }
          : { day: destino.dia }

    // Se pinta antes de que responda el servidor: soltar algo y verlo saltar
    // medio segundo después se siente roto.
    const antes = todas
    setTodas((lista) =>
      lista.map((t) =>
        t.id === task.id
          ? {
              ...t,
              week: destino.tipo === 'otras' ? null : semana,
              day: destino.tipo === 'dia' ? destino.dia : null,
            }
          : t,
      ),
    )

    try {
      await api.updateTask(task.id, cambios)
    } catch (err) {
      setTodas(antes)
      onError(err.message)
    }
  }

  async function alternar(task) {
    setTodas((lista) =>
      lista.map((t) =>
        t.id === task.id
          ? { ...t, done: !t.done, active: t.done ? t.active : false }
          : t,
      ),
    )
    try {
      await api.updateTask(task.id, { done: !task.done })
    } catch (err) {
      onError(err.message)
      cargar()
    }
  }

  const chip = {
    onToggle: alternar,
    onAbrir: (task) => setDetalle(task),
    onArrastrar: (task) => {
      arrastrada.current = task
    },
    // Solo se escribe si cambió: dragover dispara decenas de veces por
    // segundo y re-renderizar en cada una cancela el arrastre.
    onEncima: (zona) => setEncima((actual) => (actual === zona ? actual : zona)),
    onSoltar: soltar,
  }

  return (
    <div
      className={`overlay ${completa ? 'sin-fondo' : ''}`}
      onClick={completa ? undefined : onClose}
      role="presentation"
    >
      <div
        className={`modal planner ${completa ? 'pantalla-completa' : ''}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Planificar ${thread.name}`}
        // Soltar fuera de una zona no mueve nada, pero tiene que apagar el
        // resaltado igual.
        onDragEnd={() => {
          arrastrada.current = null
          setEncima(null)
        }}
      >
        <div className="modal-head">
          <span className={`pastilla color-${thread.color}`}>{thread.name}</span>
          <div className="periodo-nav">
            <button
              onClick={() => setSemana(sumarSemanas(semana, -1))}
              aria-label="Semana anterior"
            >
              ‹
            </button>
            <span className="periodo-etiqueta">{etiquetaSemana(semana)}</span>
            <button
              onClick={() => setSemana(sumarSemanas(semana, 1))}
              aria-label="Semana siguiente"
            >
              ›
            </button>
          </div>
          <span style={{ flex: 1 }} />
          <button
            className="expandir"
            onClick={() => setCompleta(!completa)}
            aria-pressed={completa}
          >
            {completa ? '⤡ Salir de pantalla completa' : '⤢ Expandir pantalla'}
          </button>
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        {cargando ? (
          <p className="cargando">Cargando…</p>
        ) : (
          <div className="planner-cuerpo">
            <div className="planner-columna">
              <Zona
                titulo="Sin bajar"
                nota="Comprometido para la semana"
                tareas={sinBajar}
                destino={{ tipo: 'semana' }}
                encima={encima}
                {...chip}
              >
                <form
                  className="nueva-tarea"
                  onSubmit={async (e) => {
                    e.preventDefault()
                    const texto = nueva.trim()
                    if (!texto) return
                    try {
                      await api.addTask(thread.id, { text: texto, week: semana })
                      setNueva('')
                      await cargar()
                    } catch (err) {
                      onError(err.message)
                    }
                  }}
                >
                  <input
                    value={nueva}
                    onChange={(e) => setNueva(e.target.value)}
                    placeholder="+ Agregar a la semana"
                    maxLength={300}
                  />
                </form>
              </Zona>

              <button className="ver-otras" onClick={() => setVerOtras(!verOtras)}>
                {verOtras ? '▾' : '▸'} Otras tareas
                {otras.length > 0 && <span className="count">{otras.length}</span>}
              </button>

              {verOtras && (
                <Zona
                  titulo="Otras tareas"
                  nota="Sin fecha"
                  tareas={otras}
                  destino={{ tipo: 'otras' }}
                  encima={encima}
                  {...chip}
                />
              )}
            </div>

            <div className="planner-dias">
              {dias.map((d) => (
                <Zona
                  key={d.fecha}
                  titulo={`${d.nombre} ${d.numero}`}
                  nota={d.fecha === hoyIso() ? 'hoy' : null}
                  tareas={delDia(d.fecha)}
                  destino={{ tipo: 'dia', dia: d.fecha }}
                  encima={encima}
                  resumido
                  {...chip}
                />
              ))}
            </div>
          </div>
        )}

        {detalle && (
          <TaskModal
            task={detalle}
            thread={thread}
            semana={semana}
            onGuardar={async (task, cambios) => {
              await api.updateTask(task.id, cambios)
              await cargar()
            }}
            onClose={() => setDetalle(null)}
            onError={onError}
          />
        )}
      </div>
    </div>
  )
}
