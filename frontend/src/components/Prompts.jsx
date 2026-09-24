import { useCallback, useEffect, useRef, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'
import CopyButton from './CopyButton.jsx'
import { useRefrescoPeriodico } from '../refresco.js'
import ProjectForm from './ProjectForm.jsx'
import PromptModal from './PromptModal.jsx'

// Principal: donde cae todo lo que dicta el bot. No es un proyecto ni un id
// real, es el filtro de "sin proyecto asignado".
//
// El bot ya no adivina el proyecto al dictar: fallaba seguido y un prompt en
// la carpeta equivocada se pierde de vista. Llegan todos aquí y de aquí se
// arrastran al proyecto que corresponde.
const PRINCIPAL = 'sueltos'

function fechaCorta(iso) {
  return new Date(iso).toLocaleDateString('es-CL', {
    day: '2-digit',
    month: 'short',
  })
}

function Tarjeta({ prompt, onAbrir, onArrastrar }) {
  return (
    <article
      className="prompt-card"
      onClick={() => onAbrir(prompt)}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', prompt.id)
        e.dataTransfer.effectAllowed = 'move'
        onArrastrar(prompt)
      }}
    >
      <h3>{prompt.title}</h3>
      {/* Las primeras líneas del prompt alcanzan para reconocerlo sin abrirlo. */}
      <p>{prompt.content}</p>
      <div className="meta">
        <span>{fechaCorta(prompt.created_at)}</span>
        {prompt.edited && <span className="badge en_curso">editado</span>}
        {!prompt.project_id && <span className="badge pendiente">sin asignar</span>}
        <span style={{ flex: 1 }} />
        {/* stopPropagation: copiar no debe abrir el detalle. */}
        <span onClick={(e) => e.stopPropagation()}>
          <CopyButton texto={prompt.content} />
        </span>
      </div>
    </article>
  )
}

export default function Prompts({ onUnauthorized, onError }) {
  const [proyectos, setProyectos] = useState([])
  const [activo, setActivo] = useState(null)
  const [prompts, setPrompts] = useState([])
  const [loading, setLoading] = useState(true)
  const [abierto, setAbierto] = useState(null)
  const [editandoProyecto, setEditandoProyecto] = useState(null)
  // El prompt que se arrastra y la pestaña sobre la que está.
  const arrastrado = useRef(null)
  const [encima, setEncima] = useState(null)

  const manejarError = useCallback(
    (err) => {
      if (err instanceof UnauthorizedError) onUnauthorized()
      else onError(err.message)
    },
    [onUnauthorized, onError],
  )

  const cargarProyectos = useCallback(async () => {
    try {
      const lista = await api.promptProjects()
      setProyectos(lista)
      setActivo((actual) => {
        if (actual === PRINCIPAL) return actual
        if (actual && lista.some((p) => p.id === actual)) return actual
        // Principal por defecto: es donde llega todo.
        return PRINCIPAL
      })
    } catch (err) {
      manejarError(err)
    }
  }, [manejarError])

  const cargarPrompts = useCallback(
    async ({ silencioso = false } = {}) => {
      if (!activo) return
      // El refresco automático no enciende el cargando ni avisa si falla: un
      // parpadeo de la grilla cada veinte segundos sería peor que esperar.
      if (!silencioso) setLoading(true)
      try {
        setPrompts(
          await api.prompts(
            activo === PRINCIPAL
              ? { sinProyecto: true }
              : { projectId: activo },
          ),
        )
      } catch (err) {
        if (!silencioso) manejarError(err)
      } finally {
        if (!silencioso) setLoading(false)
      }
    },
    [activo, manejarError],
  )

  useEffect(() => {
    cargarProyectos()
  }, [cargarProyectos])

  useEffect(() => {
    cargarPrompts()
  }, [cargarPrompts])

  // Principal recibe lo que dicta el bot mientras está abierta. Se suspende
  // con un modal encima y mientras se arrastra: re-renderizar la grilla en
  // medio de un arrastre lo cancela.
  const refrescarPrompts = useCallback(async () => {
    if (arrastrado.current) return
    await Promise.all([
      cargarPrompts({ silencioso: true }),
      cargarProyectos(),
    ])
  }, [cargarPrompts, cargarProyectos])

  useRefrescoPeriodico(refrescarPrompts, {
    activo: !abierto && !editandoProyecto,
  })

  async function refrescar() {
    await Promise.all([cargarProyectos(), cargarPrompts()])
  }

  async function guardarPrompt(prompt, cambios) {
    const actualizado = await api.updatePrompt(prompt.id, cambios)
    setPrompts((lista) =>
      lista.map((p) => (p.id === prompt.id ? actualizado : p)),
    )
    setAbierto(actualizado)
  }

  async function moverPrompt(prompt, projectId) {
    try {
      await api.updatePrompt(prompt.id, { project_id: projectId })
      setAbierto(null)
      await refrescar()
    } catch (err) {
      manejarError(err)
    }
  }

  /** Soltar un prompt sobre una pestaña lo reasigna. */
  async function soltarEn(destino) {
    const prompt = arrastrado.current
    arrastrado.current = null
    setEncima(null)
    if (!prompt) return

    const projectId = destino === PRINCIPAL ? null : destino
    if ((prompt.project_id ?? null) === projectId) return

    // Se saca de la lista al tiro: sale de la pestaña que se está mirando.
    setPrompts((lista) => lista.filter((p) => p.id !== prompt.id))
    try {
      await api.updatePrompt(prompt.id, { project_id: projectId })
      await cargarProyectos()
    } catch (err) {
      manejarError(err)
      await refrescar()
    }
  }

  async function eliminarPrompt(prompt) {
    if (!window.confirm(`¿Eliminar "${prompt.title}"?`)) return
    try {
      await api.deletePrompt(prompt.id)
      setAbierto(null)
      await refrescar()
    } catch (err) {
      manejarError(err)
    }
  }

  async function guardarProyecto(datos) {
    if (editandoProyecto === 'nuevo') {
      await api.createProject(datos.name, datos.description_md)
    } else {
      await api.updateProject(editandoProyecto.id, datos)
    }
    setEditandoProyecto(null)
    await refrescar()
  }

  async function eliminarProyecto(proyecto) {
    const { prompts_sueltos } = await api.deleteProject(proyecto.id)
    setEditandoProyecto(null)
    setActivo(null)
    await refrescar()
    if (prompts_sueltos > 0) {
      onError(
        `${prompts_sueltos} prompts quedaron sin proyecto. Están en "Sin proyecto".`,
      )
    }
  }

  const proyectoActivo = proyectos.find((p) => p.id === activo)

  return (
    <section
      className="prompts"
      onDragEnd={() => {
        arrastrado.current = null
        setEncima(null)
      }}
    >
      <div className="prompts-barra">
        <nav className="proyectos">
          {/* Cada pestaña recibe prompts arrastrados desde la que se mira. */}
          <button
            className={`bandeja-principal ${encima === PRINCIPAL ? 'encima' : ''}`}
            aria-pressed={activo === PRINCIPAL}
            onClick={() => setActivo(PRINCIPAL)}
            onDragOver={(e) => {
              e.preventDefault()
              setEncima((a) => (a === PRINCIPAL ? a : PRINCIPAL))
            }}
            onDrop={(e) => {
              e.preventDefault()
              soltarEn(PRINCIPAL)
            }}
            title="Todo lo que dicta el bot llega aquí"
          >
            Principal
          </button>

          {proyectos.map((p) => (
            <button
              key={p.id}
              className={encima === p.id ? 'encima' : ''}
              aria-pressed={activo === p.id}
              onClick={() => setActivo(p.id)}
              onDragOver={(e) => {
                // Sin preventDefault el navegador no acepta el destino. Y el
                // resaltado solo se escribe si cambió: dragover dispara
                // decenas de veces por segundo.
                e.preventDefault()
                setEncima((a) => (a === p.id ? a : p.id))
              }}
              onDrop={(e) => {
                e.preventDefault()
                soltarEn(p.id)
              }}
            >
              {p.name}
              {p.prompts_count > 0 && (
                <span className="count">{p.prompts_count}</span>
              )}
            </button>
          ))}
        </nav>

        <div className="prompts-acciones">
          {proyectoActivo && (
            <button onClick={() => setEditandoProyecto(proyectoActivo)}>
              ⚙ Contexto
            </button>
          )}
          <button onClick={() => setEditandoProyecto('nuevo')}>+ Proyecto</button>
        </div>
      </div>

      {proyectoActivo && !proyectoActivo.description_md.trim() && (
        <p className="aviso-contexto">
          Este proyecto no tiene contexto escrito. Sirve de glosario al ordenar
          lo que dictas: sin él, un nombre propio dicho a medias queda como lo
          entendió el transcriptor.{' '}
          <button
            className="ghost"
            onClick={() => setEditandoProyecto(proyectoActivo)}
          >
            Escribirlo
          </button>
        </p>
      )}

      {loading && prompts.length === 0 ? (
        <p className="cargando">Cargando…</p>
      ) : prompts.length === 0 ? (
        <p className="vacio">
          {activo === PRINCIPAL
            ? 'Principal está vacía. Mándale un audio al bot de prompts.'
            : 'Nada asignado a este proyecto. Arrastra prompts desde Principal.'}
        </p>
      ) : (
        <div className="prompts-grid">
          {prompts.map((p) => (
            <Tarjeta
              key={p.id}
              prompt={p}
              onAbrir={setAbierto}
              onArrastrar={(prompt) => {
                arrastrado.current = prompt
              }}
            />
          ))}
        </div>
      )}

      {abierto && (
        <PromptModal
          prompt={abierto}
          proyectos={proyectos}
          onClose={() => setAbierto(null)}
          onGuardar={guardarPrompt}
          onMover={moverPrompt}
          onEliminar={eliminarPrompt}
          onError={onError}
        />
      )}

      {editandoProyecto && (
        <ProjectForm
          proyecto={editandoProyecto === 'nuevo' ? null : editandoProyecto}
          onGuardar={guardarProyecto}
          onEliminar={eliminarProyecto}
          onClose={() => setEditandoProyecto(null)}
        />
      )}
    </section>
  )
}
