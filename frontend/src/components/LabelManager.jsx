import { useState } from 'react'

import { api } from '../api.js'
import { useCierreExterior } from '../cierre.js'

/** Las subcategorías de una categoría, anidadas bajo ella. */
function Subcategorias({ categoria, onChanged, onError }) {
  const [nueva, setNueva] = useState('')
  const [busy, setBusy] = useState(false)

  async function ejecutar(accion) {
    setBusy(true)
    try {
      await accion()
      await onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="subetiquetas">
      {categoria.subcategorias.map((s) => (
        <div className="etiqueta-fila" key={s.id}>
          <span className="etiqueta-nombre">{s.name}</span>
          <span className="etiqueta-usos">
            {s.usos > 0 ? `${s.usos}` : '—'}
          </span>
          <button
            disabled={busy}
            onClick={async () => {
              const nombre = window.prompt('Nuevo nombre', s.name)
              if (!nombre || nombre.trim() === s.name) return
              await ejecutar(() => api.renameSubcategory(s.id, nombre.trim()))
            }}
          >
            Renombrar
          </button>
          <button
            className="danger"
            disabled={busy || s.usos > 0}
            onClick={async () => {
              if (!window.confirm(`¿Eliminar "${s.name}"?`)) return
              await ejecutar(() => api.deleteSubcategory(s.id))
            }}
            title={s.usos > 0 ? 'Está en uso' : 'Eliminar'}
          >
            Eliminar
          </button>
        </div>
      ))}

      <form
        className="etiqueta-fila"
        onSubmit={async (e) => {
          e.preventDefault()
          const nombre = nueva.trim()
          if (!nombre) return
          await ejecutar(() => api.createSubcategory(categoria.id, nombre))
          setNueva('')
        }}
      >
        <input
          value={nueva}
          onChange={(e) => setNueva(e.target.value)}
          placeholder="Nuevo detalle"
        />
        <button disabled={busy || !nueva.trim()}>Agregar</button>
      </form>
    </div>
  )
}

function Lista({ tipo, titulo, items, onChanged, onError }) {
  const [nuevo, setNuevo] = useState('')
  const [busy, setBusy] = useState(false)

  async function ejecutar(accion) {
    setBusy(true)
    try {
      await accion()
      await onChanged()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function crear(event) {
    event.preventDefault()
    const nombre = nuevo.trim()
    if (!nombre) return
    await ejecutar(() => api.createExpenseLabel(tipo, nombre))
    setNuevo('')
  }

  async function renombrar(item) {
    const nombre = window.prompt('Nuevo nombre', item.name)
    if (!nombre || nombre.trim() === item.name) return
    await ejecutar(() => api.renameExpenseLabel(tipo, item.id, nombre.trim()))
  }

  async function eliminar(item) {
    if (!window.confirm(`¿Eliminar "${item.name}"?`)) return
    await ejecutar(() => api.deleteExpenseLabel(tipo, item.id))
  }

  return (
    <div className="campo">
      <dt>{titulo}</dt>
      <dd>
        <div className="etiquetas">
          {items.map((item) => (
            <div key={item.id}>
              <div className="etiqueta-fila">
                <span className="etiqueta-nombre">{item.name}</span>
                <span className="etiqueta-usos">
                  {item.usos > 0 ? `${item.usos} gastos` : 'sin uso'}
                </span>
                <button disabled={busy} onClick={() => renombrar(item)}>
                  Renombrar
                </button>
                <button
                  className="danger"
                  disabled={busy || item.usos > 0}
                  onClick={() => eliminar(item)}
                  title={
                    item.usos > 0
                      ? 'Está en uso: renómbrala o reasigna sus gastos primero'
                      : 'Eliminar'
                  }
                >
                  Eliminar
                </button>
              </div>

              {item.subcategorias?.length >= 0 && tipo === 'categories' && (
                <Subcategorias
                  categoria={item}
                  onChanged={onChanged}
                  onError={onError}
                />
              )}
            </div>
          ))}

          <form className="etiqueta-fila" onSubmit={crear}>
            <input
              value={nuevo}
              onChange={(e) => setNuevo(e.target.value)}
              placeholder={`Nueva ${titulo.toLowerCase()}`}
            />
            <button className="primary" disabled={busy || !nuevo.trim()}>
              Agregar
            </button>
          </form>
        </div>
      </dd>
    </div>
  )
}

/**
 * Categorías de gasto, sus subcategorías, y los medios de pago.
 *
 * Nada en uso se puede eliminar: reasignar gastos pasados falsearía el
 * historial, que es justo lo que este panel existe para conservar. Para
 * corregir un nombre está renombrar, que sí afecta a los gastos existentes.
 */
export default function LabelManager({ categorias, medios, onClose, onChanged }) {
  const [error, setError] = useState('')

  return (
    <div className="overlay" {...useCierreExterior(onClose)}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Categorías y medios de pago"
      >
        <div className="modal-head">
          <h2>Categorías y medios de pago</h2>
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="campos">
          <Lista
            tipo="categories"
            titulo="Categorías"
            items={categorias}
            onChanged={onChanged}
            onError={setError}
          />
          <Lista
            tipo="methods"
            titulo="Medios de pago"
            items={medios}
            onChanged={onChanged}
            onError={setError}
          />

          {error && <p className="login error">{error}</p>}

          <p className="nota">
            Renombrar afecta a los gastos existentes; eliminar solo se permite
            si la etiqueta no está en uso, para no falsear el historial.
          </p>
        </div>
      </div>
    </div>
  )
}
