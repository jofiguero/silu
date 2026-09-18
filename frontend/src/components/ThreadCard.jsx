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
  onToggleActive,
  onAddTask,
  onEditTask,
  onMoveTask,
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
  // El papel solo se vuelve arrastrable mientras se presiona su encabezado.
  // Con toda la tarjeta arrastrable siempre, el gesto competía con escribir en
  // el campo de tareas y con tirar de la esquina para redimensionar.
  const [asido, setAsido] = useState(false)
  // Tarea en edición y su texto provisorio.
  const [editandoId, setEditandoId] = useState(null)
  const [borrador, setBorrador] = useState('')
  const papelRef = useRef(null)

  const pendientes = thread.tasks.filter((t) => !t.done).length
  const total = thread.tasks.length
  const enCurso = thread.tasks.filter((t) => t.active && !t.done).length

  // Manda el orden que la persona dejó a mano. Antes lo activo subía solo al
  // tope, pero eso peleaba con las flechas: presionar ▲ en una tarea activa no
  // movía nada. El resaltado ya la hace visible sin reordenar.
  const ordenadas = [...thread.tasks].sort((a, b) => a.position - b.position)

  // El tamaño se guarda cuando la persona suelta el borde, no en cada píxel:
  // arrastrar la esquina dispararía decenas de peticiones.
  useEffect(() => {
    const nodo = papelRef.current
    if (!nodo) return

    let timer
    const observer = new ResizeObserver(() => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        // offsetWidth/offsetHeight y NO contentRect: contentRect excluye el
        // padding, pero al aplicarlo como width con box-sizing: border-box ese
        // valor lo incluye. Guardarlo así restaba el padding en cada vuelta y
        // encogía el papel hasta el mínimo.
        const w = nodo.offsetWidth
        const h = nodo.offsetHeight
        // Margen de 2px: evita reescribir por diferencias de redondeo.
        if (
          Math.abs(w - (thread.width ?? 0)) > 2 ||
          Math.abs(h - (thread.height ?? 0)) > 2
        ) {
          onResize(thread, w, h)
        }
      }, 700)
    })

    observer.observe(nodo)
    return () => {
      clearTimeout(timer)
      observer.disconnect()
    }
  }, [thread, onResize])

  function abrirEdicion(task) {
    setEditandoId(task.id)
    setBorrador(task.text)
  }

  async function confirmarEdicion(task) {
    const texto = borrador.trim()
    setEditandoId(null)
    // Sin cambios o vacío: se descarta en silencio en vez de borrar el texto.
    if (!texto || texto === task.text) return
    await onEditTask(task, texto)
  }

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
      ref={papelRef}
      style={{
        width: thread.width ? `${thread.width}px` : undefined,
        height: thread.height ? `${thread.height}px` : undefined,
      }}
      draggable={asido}
      onDragStart={(event) => {
        event.dataTransfer.setData('text/plain', thread.id)
        event.dataTransfer.effectAllowed = 'move'
        onDragStart(thread)
      }}
      onDragEnd={() => setAsido(false)}
      onDragOver={(event) => {
        event.preventDefault()
        onDragOver(thread)
      }}
      onDrop={(event) => {
        event.preventDefault()
        onDrop(thread)
      }}
    >
      <header
        className="posit-head"
        // El encabezado es el asa: presionarlo habilita el arrastre.
        onMouseDown={() => setAsido(true)}
        onMouseUp={() => setAsido(false)}
        title="Arrastra desde aquí para reordenar"
      >
        <span className="asa" aria-hidden="true">
          ⠿
        </span>
        <h3>{thread.name}</h3>
        <div className="posit-acciones">
          {enCurso > 0 && (
            <span className="pip" title={`${enCurso} en curso ahora`}>
              ◉
            </span>
          )}
          <span className="progreso" title="Pendientes de esta semana">
            {total > 0 ? `${total - pendientes}/${total}` : '—'}
          </span>
          <button
            className="ghost"
            // El botón no debe habilitar el arrastre al presionarlo.
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onEditar(thread)}
            aria-label={`Editar ${thread.name}`}
            title="Editar"
          >
            ⋯
          </button>
        </div>
      </header>

      <div className="posit-cuerpo">
        <ul className="tareas">
          {ordenadas.map((task, indice) => (
            <li
              key={task.id}
              className={`tarea ${task.done ? 'hecha' : ''} ${
                task.active && !task.done ? 'en-curso' : ''
              }`}
            >
              {editandoId === task.id ? (
                <input
                  className="editar-tarea"
                  value={borrador}
                  autoFocus
                  onChange={(e) => setBorrador(e.target.value)}
                  // Guarda al salir del campo: si la persona hace clic en otra
                  // parte, lo escrito no se pierde.
                  onBlur={() => confirmarEdicion(task)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      confirmarEdicion(task)
                    }
                    if (e.key === 'Escape') setEditandoId(null)
                  }}
                />
              ) : (
                <>
                  <label>
                    <input
                      type="checkbox"
                      checked={task.done}
                      onChange={() => onToggleTask(task)}
                    />
                    <span className="caja" aria-hidden="true" />
                    <span className="texto">{task.text}</span>
                  </label>
                  <span className="orden">
                    <button
                      className="mover"
                      onClick={() => onMoveTask(thread, task, -1)}
                      disabled={indice === 0}
                      aria-label={`Subir ${task.text}`}
                      title="Subir"
                    >
                      ▲
                    </button>
                    <button
                      className="mover"
                      onClick={() => onMoveTask(thread, task, 1)}
                      disabled={indice === ordenadas.length - 1}
                      aria-label={`Bajar ${task.text}`}
                      title="Bajar"
                    >
                      ▼
                    </button>
                  </span>
                  <button
                    className={`marcar ${task.active ? 'activa' : ''}`}
                    onClick={() => onToggleActive(task)}
                    aria-pressed={task.active}
                    aria-label={
                      task.active
                        ? `Dejar de trabajar en ${task.text}`
                        : `Estoy trabajando en ${task.text}`
                    }
                    title={
                      task.active ? 'Ya no estoy en esto' : 'Estoy en esto ahora'
                    }
                  >
                    ◉
                  </button>
                  <button
                    className="quitar"
                    onClick={() => abrirEdicion(task)}
                    aria-label={`Editar ${task.text}`}
                    title="Editar"
                  >
                    ✎
                  </button>
                  <button
                    className="quitar"
                    onClick={() => onDeleteTask(task)}
                    aria-label={`Eliminar ${task.text}`}
                    title="Eliminar"
                  >
                    ×
                  </button>
                </>
              )}
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
