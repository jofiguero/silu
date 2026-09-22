import { useCallback, useEffect, useRef, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'
import BacklogDrawer from './BacklogDrawer.jsx'
import TaskModal from './TaskModal.jsx'
import ThreadCard from './ThreadCard.jsx'
import ThreadForm from './ThreadForm.jsx'
import {
  desdeIso,
  etiquetaSemana,
  etiquetaDia,
  hoyIso,
  iso,
  lunesDe,
  semanaActual,
  sumarSemanas,
} from '../semana.js'

function sumarDias(diaIso, cuantos) {
  const fecha = desdeIso(diaIso)
  fecha.setDate(fecha.getDate() + cuantos)
  return iso(fecha)
}

/** Panel de tareas: un papel adhesivo por frente de trabajo. */
export default function Dashboard({ onUnauthorized, onError }) {
  const [threads, setThreads] = useState([])
  const [colores, setColores] = useState([])
  const [loading, setLoading] = useState(true)
  const [editando, setEditando] = useState(null) // thread | 'nuevo' | null
  const [limpiando, setLimpiando] = useState(false)
  // La tarea abierta en el detalle: {thread, task} para editar, o
  // {thread, task: null} para crear una nueva con descripción.
  const [detalle, setDetalle] = useState(null)

  // Qué se está mirando. Arranca en el día: es la vista que se consulta
  // muchas veces al día, mientras que la semanal se mira una o dos.
  const [vista, setVista] = useState('dia')
  const [dia, setDia] = useState(hoyIso())
  const [semana, setSemana] = useState(semanaActual())
  // El thread cuyo cajón de "otras tareas" está abierto.
  const [otras, setOtras] = useState(null)

  // El thread que se arrastra y sobre cuál está, para reordenar al soltar.
  const arrastrado = useRef(null)
  const [encima, setEncima] = useState(null)

  const manejarError = useCallback(
    (err) => {
      if (err instanceof UnauthorizedError) onUnauthorized()
      else onError(err.message)
    },
    [onUnauthorized, onError],
  )

  const cargar = useCallback(async () => {
    try {
      const lista =
        vista === 'dia'
          ? await api.threads({ scope: 'day', day: dia })
          : await api.threads({ scope: 'week', week: semana })

      // Lo atrasado se marca aquí y no en el backend: es una lectura de la
      // fecha contra hoy, no un dato de la tarea. La tarea conserva su día.
      setThreads(
        lista.map((t) => ({
          ...t,
          tasks: t.tasks.map((x) => ({
            ...x,
            atrasada: vista === 'dia' && x.day !== dia && !x.done,
          })),
        })),
      )
    } catch (err) {
      manejarError(err)
    } finally {
      setLoading(false)
    }
  }, [manejarError, vista, dia, semana])

  useEffect(() => {
    cargar()
  }, [cargar])

  useEffect(() => {
    api.threadColors().then(setColores).catch(() => {})
  }, [])

  /** Si una tarea recién guardada sigue perteneciendo a lo que se mira. */
  const enLaVista = useCallback(
    (tarea) =>
      vista === 'dia'
        ? tarea.day === dia || (dia === hoyIso() && tarea.day && tarea.day < dia)
        : tarea.week === semana,
    [vista, dia, semana],
  )

  // --- Tareas ---

  async function alternar(task) {
    // Se cambia en pantalla antes de que responda el servidor: la animación
    // del tachado tiene que salir al instante del clic, no medio segundo
    // después. Si falla, se recarga y vuelve a su estado real.
    setThreads((actuales) =>
      actuales.map((t) => ({
        ...t,
        tasks: t.tasks.map((x) =>
          x.id === task.id
            ? // Terminar algo implica dejar de estar en ello; el backend hace
              // lo mismo, y reflejarlo aquí evita un parpadeo.
              { ...x, done: !x.done, active: x.done ? x.active : false }
            : x,
        ),
      })),
    )
    try {
      await api.updateTask(task.id, { done: !task.done })
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  async function alternarEnCurso(task) {
    const ahora = !task.active
    setThreads((actuales) =>
      actuales.map((t) => ({
        ...t,
        tasks: t.tasks.map((x) =>
          x.id === task.id ? { ...x, active: ahora } : x,
        ),
      })),
    )
    try {
      await api.updateTask(task.id, { active: ahora })
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  async function agregarTarea(thread, datos) {
    const base = typeof datos === 'string' ? { text: datos } : datos
    // Escribir una tarea en la vista diaria es escribirla para ese día, y eso
    // la mete en la semana sola. En la semanal, para la semana que se mira.
    const cuerpo =
      base.backlog || base.day || base.week
        ? base
        : vista === 'dia'
          ? { ...base, day: dia }
          : { ...base, week: semana }

    const tarea = await api.addTask(thread.id, cuerpo)

    // Una tarea creada para "otras tareas" o para otro momento no pertenece a
    // lo que se está mirando, aunque se haya escrito desde aquí.
    if (!enLaVista(tarea)) return

    setThreads((actuales) =>
      actuales.map((t) =>
        t.id === thread.id ? { ...t, tasks: [...t.tasks, tarea] } : t,
      ),
    )
  }

  async function editarTarea(task, cambios) {
    // El detalle espera la respuesta antes de cerrarse, así que aquí no se
    // pinta por adelantado: se aplica lo que el servidor confirmó.
    const actualizada = await api.updateTask(task.id, cambios)

    // Si dejó de pertenecer a lo que se mira, ya no va en el pizarrón:
    // reemplazarla en su sitio la dejaría visible hasta la próxima recarga.
    if (!enLaVista(actualizada)) {
      await cargar()
      return
    }

    setThreads((actuales) =>
      actuales.map((t) => ({
        ...t,
        tasks: t.tasks.map((x) => (x.id === task.id ? actualizada : x)),
      })),
    )
  }

  async function moverTarea(thread, task, delta) {
    const actuales = [...thread.tasks].sort((a, b) => a.position - b.position)
    const desde = actuales.findIndex((t) => t.id === task.id)
    const hasta = desde + delta
    if (desde < 0 || hasta < 0 || hasta >= actuales.length) return

    const nuevas = [...actuales]
    ;[nuevas[desde], nuevas[hasta]] = [nuevas[hasta], nuevas[desde]]
    // Las posiciones se reescriben aquí también: si solo se reordenara el
    // arreglo, el siguiente movimiento partiría de posiciones viejas.
    const conPosicion = nuevas.map((t, i) => ({ ...t, position: i }))

    setThreads((lista) =>
      lista.map((t) => (t.id === thread.id ? { ...t, tasks: conPosicion } : t)),
    )

    try {
      await api.reorderTasks(thread.id, conPosicion.map((t) => t.id))
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  async function eliminarTarea(task) {
    setThreads((actuales) =>
      actuales.map((t) => ({
        ...t,
        tasks: t.tasks.filter((x) => x.id !== task.id),
      })),
    )
    try {
      await api.deleteTask(task.id)
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  // --- Threads ---

  async function guardar(datos) {
    if (editando === 'nuevo') await api.createThread(datos.name, datos.color)
    else await api.updateThread(editando.id, datos)
    setEditando(null)
    await cargar()
  }

  async function eliminarThread(thread) {
    await api.deleteThread(thread.id)
    setEditando(null)
    await cargar()
  }

  async function redimensionar(thread, width, height) {
    try {
      await api.updateThread(thread.id, { width, height })
      setThreads((actuales) =>
        actuales.map((t) => (t.id === thread.id ? { ...t, width, height } : t)),
      )
    } catch (err) {
      manejarError(err)
    }
  }

  async function soltar(destino) {
    const origen = arrastrado.current
    arrastrado.current = null
    setEncima(null)
    if (!origen || origen.id === destino.id) return

    // Se reordena en pantalla y se manda el orden completo: mandar la lista
    // entera evita que dos reacomodos seguidos dejen posiciones inconsistentes.
    const sinOrigen = threads.filter((t) => t.id !== origen.id)
    const indice = sinOrigen.findIndex((t) => t.id === destino.id)
    const nuevo = [
      ...sinOrigen.slice(0, indice),
      origen,
      ...sinOrigen.slice(indice),
    ]
    setThreads(nuevo)

    try {
      await api.reorderThreads(nuevo.map((t) => t.id))
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  async function limpiar() {
    const tachadas = threads.reduce(
      (suma, t) => suma + t.tasks.filter((x) => x.done).length,
      0,
    )
    if (tachadas === 0) {
      onError('No hay nada tachado que limpiar.')
      return
    }
    if (
      !window.confirm(
        `Se sacan del pizarrón ${tachadas} tareas tachadas. Quedan guardadas, no se borran. ¿Limpiar?`,
      )
    )
      return

    setLimpiando(true)
    try {
      await api.cleanupBoard()
      await cargar()
    } catch (err) {
      manejarError(err)
    } finally {
      setLimpiando(false)
    }
  }

  const tachadas = threads.reduce(
    (suma, t) => suma + t.tasks.filter((x) => x.done).length,
    0,
  )
  const enCurso = threads.reduce(
    (suma, t) => suma + t.tasks.filter((x) => x.active && !x.done).length,
    0,
  )

  return (
    <section className="dashboard">
      <div className="dashboard-barra">
        <div>
          <h2>{vista === 'dia' ? etiquetaDia(dia) : etiquetaSemana(semana)}</h2>
          <p className="nota">
            {vista === 'dia'
              ? 'Lo que baja al día de hoy. Lo que quedó pendiente antes sigue aquí, con su fecha.'
              : 'Lo que hay que mover sí o sí. Macro tareas, no la lista larga.'}
            {enCurso > 0 && (
              <>
                {' · '}
                <strong className="nota-curso">
                  {enCurso} en curso ahora
                </strong>
              </>
            )}
          </p>
        </div>
        <div className="dashboard-acciones">
          <button onClick={() => setEditando('nuevo')}>+ Thread</button>
          <button
            className="limpiar"
            onClick={limpiar}
            disabled={limpiando || tachadas === 0}
            title="Saca del pizarrón lo tachado, sin borrarlo"
          >
            🧹 Limpiar
            {tachadas > 0 && <span className="count">{tachadas}</span>}
          </button>
        </div>
      </div>

      <div className="dashboard-nav">
        {/* El switch y la navegación: la misma pared de papeles, filtrada por
            el momento que se está mirando. */}
        <div className="vistas">
          <button
            aria-pressed={vista === 'dia'}
            onClick={() => {
              setVista('dia')
              setDia(hoyIso())
            }}
          >
            Día
          </button>
          <button
            aria-pressed={vista === 'semana'}
            onClick={() => {
              setVista('semana')
              // Se abre en la semana del día que se estaba mirando: pasar de
              // un jueves a otra semana cualquiera sería desconcertante.
              setSemana(iso(lunesDe(desdeIso(dia))))
            }}
          >
            Semana
          </button>
        </div>

        <div className="periodo-nav">
          <button
            onClick={() =>
              vista === 'dia' ? setDia(sumarDias(dia, -1)) : setSemana(sumarSemanas(semana, -1))
            }
            aria-label="Anterior"
          >
            ‹
          </button>
          <button
            className="volver-hoy"
            onClick={() => {
              setDia(hoyIso())
              setSemana(semanaActual())
            }}
            disabled={vista === 'dia' ? dia === hoyIso() : semana === semanaActual()}
          >
            {vista === 'dia' ? 'Hoy' : 'Esta semana'}
          </button>
          <button
            onClick={() =>
              vista === 'dia' ? setDia(sumarDias(dia, 1)) : setSemana(sumarSemanas(semana, 1))
            }
            aria-label="Siguiente"
          >
            ›
          </button>
        </div>
      </div>

      {loading ? (
        <p className="cargando">Cargando…</p>
      ) : threads.length === 0 ? (
        <p className="vacio">
          No hay threads todavía. Crea el primero con “+ Thread”.
        </p>
      ) : (
        <div className="pizarron">
          {threads.map((thread) => (
            <ThreadCard
              key={thread.id}
              thread={thread}
              arrastrando={encima === thread.id}
              onToggleTask={alternar}
              onToggleActive={alternarEnCurso}
              onAddTask={agregarTarea}
              onAbrirTarea={(task) => setDetalle({ thread, task })}
              onNuevaTarea={(t) => setDetalle({ thread: t, task: null })}
              onMoveTask={moverTarea}
              onDeleteTask={eliminarTarea}
              onEditar={setEditando}
              onOtrasTareas={setOtras}
              diaVisto={vista === 'dia' ? dia : null}
              onResize={redimensionar}
              onDragStart={(t) => {
                arrastrado.current = t
              }}
              // Solo se actualiza si cambió el destino: dragover dispara
              // decenas de veces por segundo y re-renderizar el tablero en
              // cada una cancela el arrastre.
              onDragOver={(t) =>
                setEncima((actual) => (actual === t.id ? actual : t.id))
              }
              onDrop={soltar}
            />
          ))}
        </div>
      )}

      {otras && (
        <BacklogDrawer
          thread={otras}
          onClose={() => setOtras(null)}
          onChanged={cargar}
          onError={onError}
        />
      )}

      {detalle && (
        <TaskModal
          task={detalle.task}
          thread={detalle.thread}
          semana={semana}
          diaPorDefecto={vista === 'dia' ? dia : null}
          onGuardar={editarTarea}
          onCrear={agregarTarea}
          onClose={() => setDetalle(null)}
          onError={onError}
        />
      )}

      {editando && (
        <ThreadForm
          thread={editando === 'nuevo' ? null : editando}
          colores={colores}
          onGuardar={guardar}
          onEliminar={eliminarThread}
          onClose={() => setEditando(null)}
        />
      )}
    </section>
  )
}
