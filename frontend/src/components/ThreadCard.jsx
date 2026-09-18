import { useEffect, useRef, useState } from 'react'

/**
 * Un frente de trabajo, dibujado como papel adhesivo.
 *
 * Se puede arrastrar para reordenar el pizarrón y redimensionar tirando de la
 * esquina. Ambas cosas se guardan: reacomodar el tablero cada vez que se abre
 * sería trabajo perdido.
 */
export default function ThreadCard({
  thread,
  onToggleTask,
  onAddTask,
  onDeleteTask,
  onEditar,
  onResize,
  onDragStart,
  onDragOver,
  onDrop,
  arrastrando,
}) {
  const [nueva, setNueva] = useState('')
  const [agregando, setAgregando] = useState(false)
  const cuerpoRef = useRef(null)

  const pendientes = thread.tasks.filter((t) => !t.done).length
  const total = thread.tasks.length

  // El tamaño se guarda cuando la persona suelta el borde, no en cada píxel:
  // arrastrar la esquina dispararía decenas de peticiones.
  useEffect(() => {
    const nodo = cuerpoRef.current
    if (!nodo) return

    let timer
    const observer = new ResizeObserver(([entrada]) => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        const { width, height } = entrada.contentRect
        const w = Math.round(width)
        const h = Math.round(height)
        if (w !== thread.width || h !== thread.height) onResize(thread, w, h)
      }, 600)
    })

    observer.observe(nodo)
    return () => {
      clearTimeout(timer)
      observer.disconnect()
    }
  }, [thread, onResize])

  async function agregar(event) {
    event.preventDefault()
    const texto = nueva.trim()
    if (!texto) return
    setAgregando(true)
    try {
      await onAddTask(thread, texto)
      setNueva('')
    } finally {
      setAgregando(false)
    }
  }

  return (
    <article
      className={`posit color-${thread.color} ${arrastrando ? 'arrastrando' : ''}`}
      style={{
        width: thread.width ? `${thread.width}px` : undefined,
      }}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData('text/plain', thread.id)
        event.dataTransfer.effectAllowed = 'move'
        onDragStart(thread)
      }}
      onDragOver={(event) => {
        event.preventDefault()
        onDragOver(thread)
      }}
      onDrop={(event) => {
        event.preventDefault()
        onDrop(thread)
      }}
    >
      <header className="posit-head">
        <h3>{thread.name}</h3>
        <div className="posit-acciones">
          <span className="progreso" title="Pendientes de esta semana">
            {total > 0 ? `${total - pendientes}/${total}` : '—'}
          </span>
          <button
            className="ghost"
            onClick={() => onEditar(thread)}
            aria-label={`Editar ${thread.name}`}
            title="Editar"
          >
            ⋯
          </button>
        </div>
      </header>

      <div
        className="posit-cuerpo"
        ref={cuerpoRef}
        style={{ height: thread.height ? `${thread.height}px` : undefined }}
      >
        <ul className="tareas">
          {thread.tasks.map((task) => (
            <li key={task.id} className={`tarea ${task.done ? 'hecha' : ''}`}>
              <label>
                <input
                  type="checkbox"
                  checked={task.done}
                  onChange={() => onToggleTask(task)}
                />
                <span className="caja" aria-hidden="true" />
                <span className="texto">{task.text}</span>
              </label>
              <button
                className="quitar"
                onClick={() => onDeleteTask(task)}
                aria-label={`Eliminar ${task.text}`}
                title="Eliminar"
              >
                ×
              </button>
            </li>
          ))}

          {total === 0 && (
            <li className="sin-tareas">Nada anotado para esta semana.</li>
          )}
        </ul>

        <form className="nueva-tarea" onSubmit={agregar}>
          <input
            value={nueva}
            onChange={(e) => setNueva(e.target.value)}
            placeholder="+ Agregar"
            disabled={agregando}
          />
        </form>
      </div>
    </article>
  )
}
