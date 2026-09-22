import { useState } from 'react'
import { useCierreExterior } from '../cierre.js'

const PLANTILLA = `## De qué se trata

## Stack y herramientas

## Convenciones del proyecto

## Cosas que hay que respetar
`

/**
 * Crear o editar un proyecto con su contexto.
 *
 * El descriptor es lo único que el metaprompter sabe del proyecto, así que la
 * calidad de los prompts depende directamente de lo que se escriba aquí.
 */
export default function ProjectForm({ proyecto, onGuardar, onEliminar, onClose }) {
  const editando = Boolean(proyecto)
  const [nombre, setNombre] = useState(proyecto?.name ?? '')
  const [descripcion, setDescripcion] = useState(proyecto?.description_md ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function guardar(event) {
    event.preventDefault()
    const limpio = nombre.trim()
    if (!limpio) return
    setBusy(true)
    setError('')
    try {
      await onGuardar({ name: limpio, description_md: descripcion })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  async function eliminar() {
    const aviso =
      proyecto.prompts_count > 0
        ? `"${proyecto.name}" tiene ${proyecto.prompts_count} prompts. No se borran: quedan en "Sin proyecto". ¿Eliminar el proyecto?`
        : `¿Eliminar "${proyecto.name}"?`
    if (!window.confirm(aviso)) return
    setBusy(true)
    try {
      await onEliminar(proyecto)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="overlay" {...useCierreExterior(onClose)}>
      <form
        className="modal prompt-modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={guardar}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-head">
          <h2>{editando ? 'Contexto del proyecto' : 'Nuevo proyecto'}</h2>
          <button
            type="button"
            className="cerrar"
            onClick={onClose}
            aria-label="Cerrar"
          >
            ×
          </button>
        </div>

        <div className="campos">
          <div className="campo">
            <dt>Nombre</dt>
            <dd>
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Chilean2Sign"
                autoFocus={!editando}
              />
              <p className="nota">
                Este es el nombre que tienes que decir en el audio para que el
                prompt caiga aquí.
              </p>
            </dd>
          </div>

          <div className="campo">
            <dt>Contexto (Markdown)</dt>
            <dd>
              <textarea
                className="prompt-editor"
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                placeholder="De qué trata, qué stack usa, qué convenciones sigue…"
              />
              {!descripcion.trim() && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => setDescripcion(PLANTILLA)}
                >
                  Usar una plantilla
                </button>
              )}
              <p className="nota">
                Es lo único que el metaprompter sabe del proyecto. Mientras más
                concreto —stack, convenciones, decisiones ya tomadas— mejores
                salen los prompts.
              </p>
            </dd>
          </div>

          {error && <p className="login error">{error}</p>}

          <div className="acciones-modal">
            {editando && (
              <button
                type="button"
                className="danger"
                onClick={eliminar}
                disabled={busy}
              >
                Eliminar
              </button>
            )}
            <span style={{ flex: 1 }} />
            <button className="primary" disabled={busy || !nombre.trim()}>
              {busy ? 'Guardando…' : 'Guardar'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
