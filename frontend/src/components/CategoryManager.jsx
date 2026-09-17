import { useState } from 'react'

import { api } from '../api.js'

/**
 * Crear, renombrar y eliminar líneas de vida.
 *
 * El agente no puede hacer esto a propósito: son la estructura del sistema, no
 * datos del día a día, y una categoría creada por error ensucia el clasificador.
 */
export default function CategoryManager({ categories, onClose, onChanged }) {
  const [nueva, setNueva] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function ejecutar(accion) {
    setBusy(true)
    setError('')
    try {
      await accion()
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function crear(event) {
    event.preventDefault()
    const nombre = nueva.trim()
    if (!nombre) return
    await ejecutar(() => api.createCategory(nombre))
    setNueva('')
  }

  async function renombrar(categoria) {
    const nombre = window.prompt('Nuevo nombre', categoria.name)
    if (!nombre || nombre === categoria.name) return
    await ejecutar(() => api.renameCategory(categoria.id, nombre.trim()))
  }

  async function eliminar(categoria) {
    const aviso =
      categoria.open_count > 0
        ? `"${categoria.name}" tiene ${categoria.open_count} tickets. Se moverán a la Bandeja. ¿Eliminar la categoría?`
        : `¿Eliminar "${categoria.name}"?`
    if (!window.confirm(aviso)) return
    await ejecutar(() => api.deleteCategory(categoria.id))
  }

  return (
    <div className="overlay" onClick={onClose} role="presentation">
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Categorías"
      >
        <div className="modal-head">
          <h2>Líneas de vida</h2>
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="campos">
          {categories.map((categoria) => (
            <div className="cat-fila" key={categoria.id}>
              <span style={{ flex: 1 }}>
                {categoria.name}
                <span className="count"> · {categoria.open_count}</span>
              </span>
              <button disabled={busy} onClick={() => renombrar(categoria)}>
                Renombrar
              </button>
              {categoria.is_default ? (
                <span className="fija">fija</span>
              ) : (
                <button
                  className="danger"
                  disabled={busy}
                  onClick={() => eliminar(categoria)}
                >
                  Eliminar
                </button>
              )}
            </div>
          ))}

          <form className="cat-fila" onSubmit={crear}>
            <input
              value={nueva}
              onChange={(e) => setNueva(e.target.value)}
              placeholder="Nueva línea de vida"
            />
            <button className="primary" disabled={busy || !nueva.trim()}>
              Crear
            </button>
          </form>

          {error && <p className="login error">{error}</p>}

          <p className="nota">
            La Bandeja no se puede eliminar: es donde caen los tickets sin
            clasificar. Al borrar una categoría, sus tickets se mueven ahí.
          </p>
          <p className="nota">
            El bot usa estos nombres para clasificar lo que dictas, así que
            cambian el comportamiento de la captura de inmediato.
          </p>
        </div>
      </div>
    </div>
  )
}
