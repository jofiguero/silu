import { useState } from 'react'
import { useCierreExterior } from '../cierre.js'

/** Crear, renombrar o eliminar una carpeta de reuniones. */
export default function MeetingFolderForm({ carpeta, onGuardar, onEliminar, onClose }) {
  const editando = Boolean(carpeta)
  const [nombre, setNombre] = useState(carpeta?.name ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function guardar(event) {
    event.preventDefault()
    const limpio = nombre.trim()
    if (!limpio) return
    setBusy(true)
    setError('')
    try {
      await onGuardar(limpio)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  async function eliminar() {
    // Al revés de los proyectos de prompts, aquí no queda nada suelto: una
    // reunión sin carpeta no tiene dónde verse. Por eso el aviso lo dice.
    const aviso =
      carpeta.meetings_count > 0
        ? `"${carpeta.name}" tiene ${carpeta.meetings_count} reuniones y se borran con ella. ¿Eliminar?`
        : `¿Eliminar "${carpeta.name}"?`
    if (!window.confirm(aviso)) return
    setBusy(true)
    try {
      await onEliminar(carpeta)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="overlay" {...useCierreExterior(onClose)}>
      <form
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={guardar}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-head">
          <h2>{editando ? 'Carpeta' : 'Nueva carpeta'}</h2>
          <button type="button" className="cerrar" onClick={onClose} aria-label="Cerrar">
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
                placeholder="Reuniones con Leonardo"
                maxLength={80}
                autoFocus
              />
            </dd>
          </div>

          {error && <p className="login error">{error}</p>}

          <div className="acciones-modal">
            {editando && (
              <button type="button" className="danger" onClick={eliminar} disabled={busy}>
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
