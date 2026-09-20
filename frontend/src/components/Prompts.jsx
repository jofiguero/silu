import { useCallback, useEffect, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'
import CopyButton from './CopyButton.jsx'
import ProjectForm from './ProjectForm.jsx'
import PromptModal from './PromptModal.jsx'

// Valor del selector para los prompts que quedaron sin proyecto. No es un id
// real: es un filtro más.
const SIN_PROYECTO = 'sueltos'

function fechaCorta(iso) {
  return new Date(iso).toLocaleDateString('es-CL', {
    day: '2-digit',
    month: 'short',
  })
}

function Tarjeta({ prompt, onAbrir }) {
  return (
    <article className="prompt-card" onClick={() => onAbrir(prompt)}>
      <h3>{prompt.title}</h3>
      {/* Las primeras líneas del prompt alcanzan para reconocerlo sin abrirlo. */}
      <p>{prompt.content}</p>
      <div className="meta">
        <span>{fechaCorta(prompt.created_at)}</span>
        {prompt.edited && <span className="badge en_curso">editado</span>}
        {!prompt.project_id && <span className="badge pendiente">sin proyecto</span>}
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
        if (actual === SIN_PROYECTO) return actual
        if (actual && lista.some((p) => p.id === actual)) return actual
        return lista[0]?.id ?? SIN_PROYECTO
      })
    } catch (err) {
      manejarError(err)
    }
  }, [manejarError])

  const cargarPrompts = useCallback(async () => {
    if (!activo) return
    setLoading(true)
    try {
      setPrompts(
        await api.prompts(
          activo === SIN_PROYECTO
            ? { sinProyecto: true }
            : { projectId: activo },
        ),
      )
    } catch (err) {
      manejarError(err)
    } finally {
      setLoading(false)
    }
  }, [activo, manejarError])

  useEffect(() => {
    cargarProyectos()
  }, [cargarProyectos])

  useEffect(() => {
    cargarPrompts()
  }, [cargarPrompts])

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
    <section className="prompts">
      <div className="prompts-barra">
        <nav className="proyectos">
          {proyectos.map((p) => (
            <button
              key={p.id}
              aria-pressed={activo === p.id}
              onClick={() => setActivo(p.id)}
            >
              {p.name}
              {p.prompts_count > 0 && (
                <span className="count">{p.prompts_count}</span>
              )}
            </button>
          ))}
          <button
            aria-pressed={activo === SIN_PROYECTO}
            onClick={() => setActivo(SIN_PROYECTO)}
            title="Prompts que quedaron sin asignar"
          >
            Sin proyecto
          </button>
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
          Este proyecto no tiene contexto escrito. El metaprompter no sabe de qué
          trata, así que los prompts van a salir genéricos.{' '}
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
          {activo === SIN_PROYECTO
            ? 'No hay prompts sueltos.'
            : 'Todavía no hay prompts aquí. Mándale un audio al bot de prompts.'}
        </p>
      ) : (
        <div className="prompts-grid">
          {prompts.map((p) => (
            <Tarjeta key={p.id} prompt={p} onAbrir={setAbierto} />
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
