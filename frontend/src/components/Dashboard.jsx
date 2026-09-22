import { useCallback, useEffect, useRef, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'
import BacklogDrawer from './BacklogDrawer.jsx'
import TaskModal from './TaskModal.jsx'
import ThreadCard from './ThreadCard.jsx'
import ThreadForm from './ThreadForm.jsx'
import { semanaActual } from '../semana.js'

/** Panel de tareas: un papel adhesivo por frente de trabajo de la semana. */
export default function Dashboard({ onUnauthorized, onError }) {
  const [threads, setThreads] = useState([])
  const [colores, setColores] = useState([])
  const [loading, setLoading] = useState(true)
  const [editando, setEditando] = useState(null) // thread | 'nuevo' | null
  const [limpiando, setLimpiando] = useState(false)
  // La tarea abierta en el detalle: {thread, task} para editar, o
  // {thread, task: null} para crear una nueva con descripción.
  const [detalle, setDetalle] = useState(null)
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
      const lista = await api.threads()
      setThreads(lista)
    } catch (err) {
      manejarError(err)
    } finally {
      setLoading(false)
    }
  }, [manejarError])

  useEffect(() => {
    cargar()
    api.threadColors().then(setColores).catch(() => {})
  }, [cargar])

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
    const tarea = await api.addTask(thread.id, datos)

    // Una tarea creada para "otras tareas" o para otra semana no pertenece a
    // este pizarrón, aunque se haya escrito desde aquí.
    if (tarea.week !== semanaActual()) return

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

    // Si dejó de pertenecer a la semana en curso, ya no va en el pizarrón:
    // reemplazarla en su sitio la dejaría visible hasta la próxima recarga.
    if (actualizada.week !== semanaActual()) {
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
          <h2>Esta semana</h2>
          <p className="nota">
            Lo que hay que mover sí o sí. Macro tareas, no la lista larga.
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
