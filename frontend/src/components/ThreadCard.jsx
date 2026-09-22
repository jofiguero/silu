import { useEffect, useRef, useState } from 'react'

import { etiquetaDia } from '../semana.js'

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
  onAbrirTarea,
  onNuevaTarea,
  onMoveTask,
  onDeleteTask,
  onEditar,
  onOtrasTareas,
  diaVisto,
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
  const papelRef = useRef(null)

  const pendientes = thread.tasks.filter((t) => !t.done).length
  const total = thread.tasks.length
  const enCurso = thread.tasks.filter((t) => t.active && !t.done).length

  // Manda el orden que la persona dejó a mano. Antes lo activo subía solo al
  // tope, pero eso peleaba con las flechas: presionar ▲ en una tarea activa no
  // movía nada. El resaltado ya la hace visible sin reordenar.
  //
  // Lo atrasado es la excepción: va arriba, porque es lo que se arrastra de
  // días anteriores y tiene que verse antes que lo de hoy.
  const ordenadas = [...thread.tasks].sort(
    (a, b) => Number(!!b.atrasada) - Number(!!a.atrasada) || a.position - b.position,
  )

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
          {/* Lo que hay que hacer en este thread pero no esta semana. Vive
              fuera del papel a propósito: el pizarrón solo sirve si lo que
              está ahí es lo que hay que mover sí o sí. */}
          <button
            className="ghost"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onOtrasTareas(thread)}
            aria-label={`Otras tareas de ${thread.name}`}
            title="Otras tareas: lo que no alcanza esta semana"
          >
            ▤
          </button>
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
              } ${task.atrasada ? 'atrasada' : ''}`}
            >
              <label>
                <input
                  type="checkbox"
                  checked={task.done}
                  onChange={() => onToggleTask(task)}
                />
                <span className="caja" aria-hidden="true" />
              </label>

              {/* El texto abre el detalle; marcar es la casilla. Antes el
                  texto también marcaba, pero con un detalle que lo contiene
                  todo hacía falta una forma de llegar a él. */}
              <button
                className="texto-tarea"
                onClick={() => onAbrirTarea(task)}
                title="Abrir detalle"
              >
                <span className="texto">{task.text}</span>
                {/* La tarea está en la semana y además bajada a un día: es la
                    misma fila, así que aquí solo se muestra a cuál. Mirando un
                    día, marcar "hoy" en todas sería ruido: solo se muestra
                    cuando la fecha NO es la que se está mirando, que es
                    justamente el caso de lo atrasado. */}
                {task.day && task.day !== diaVisto && (
                  <span className={`dia-tarea ${task.atrasada ? 'vencida' : ''}`}>
                    {etiquetaDia(task.day)}
                  </span>
                )}
                {task.description && (
                  <span className="tiene-detalle" aria-label="Tiene descripción">
                    ≡
                  </span>
                )}
              </button>

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
                title={task.active ? 'Ya no estoy en esto' : 'Estoy en esto ahora'}
              >
                ◉
              </button>

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
            <li className="sin-tareas">
              {diaVisto ? 'Nada para este día.' : 'Nada anotado para esta semana.'}
            </li>
          )}
        </ul>

        <form className="nueva-tarea" onSubmit={agregar}>
          <input
            value={nueva}
            onChange={(e) => setNueva(e.target.value)}
            placeholder="+ Agregar"
            disabled={agregando}
            title={
              diaVisto
                ? 'Se agrega a este día, y entra a la semana sola'
                : 'Se agrega a la semana que estás mirando'
            }
          />
          {/* El campo de arriba es el camino rápido; este abre el detalle para
              escribir también la descripción. */}
          <button
            type="button"
            className="con-detalle"
            onClick={() => onNuevaTarea(thread)}
            title="Nueva tarea con descripción"
          >
            ⊞
          </button>
        </form>
      </div>
    </article>
  )
}
