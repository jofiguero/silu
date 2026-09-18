import { useState } from 'react'

/** Crear o editar un frente de trabajo, con su color. */
export default function ThreadForm({ thread, colores, onGuardar, onEliminar, onClose }) {
  const editando = Boolean(thread)
  const [nombre, setNombre] = useState(thread?.name ?? '')
  const [color, setColor] = useState(thread?.color ?? colores[0] ?? 'arena')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function guardar(event) {
    event.preventDefault()
    const limpio = nombre.trim()
    if (!limpio) return
    setBusy(true)
    setError('')
    try {
      await onGuardar({ name: limpio, color })
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  async function eliminar() {
    const aviso =
      thread.tasks.length > 0
        ? `"${thread.name}" tiene ${thread.tasks.length} tareas. Se eliminan junto con el thread. ¿Seguir?`
        : `¿Eliminar "${thread.name}"?`
    if (!window.confirm(aviso)) return
    setBusy(true)
    try {
      await onEliminar(thread)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose} role="presentation">
      <form
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={guardar}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-head">
          <h2>{editando ? 'Editar thread' : 'Nuevo thread'}</h2>
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
                placeholder="Guitarra, ICAI, Chilean2Sign…"
                autoFocus
              />
            </dd>
          </div>

          <div className="campo">
            <dt>Color</dt>
            <dd>
              <div className="paleta">
                {colores.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className={`muestra color-${c}`}
                    aria-pressed={color === c}
                    aria-label={c}
                    title={c}
                    onClick={() => setColor(c)}
                  />
                ))}
              </div>
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
