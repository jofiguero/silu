import { useEffect, useRef, useState } from 'react'

import { hoy } from '../periodos.js'

/**
 * Alta rápida de un gasto.
 *
 * Los tres campos obligatorios están a la vista y el foco parte en el monto:
 * registrar algo recién pagado tiene que costar escribir un número y dos
 * clics, no navegar un formulario.
 */
export default function ExpenseForm({
  categorias,
  medios,
  descripcionInicial = '',
  onGuardar,
  onGestionar,
}) {
  const [monto, setMonto] = useState('')
  const [categoria, setCategoria] = useState(null)
  const [medio, setMedio] = useState(null)
  const [fecha, setFecha] = useState(hoy())
  const [descripcion, setDescripcion] = useState(descripcionInicial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const montoRef = useRef(null)

  // Se preseleccionan los primeros: con una sola opción de medio de pago,
  // obligar a elegirla sería un clic sin información.
  useEffect(() => {
    if (!categoria && categorias.length) setCategoria(categorias[0].id)
  }, [categorias, categoria])

  useEffect(() => {
    if (!medio && medios.length) setMedio(medios[0].id)
  }, [medios, medio])

  async function enviar(event) {
    event.preventDefault()
    // Se aceptan puntos y espacios al escribir: "12.500" es como se escribe un
    // monto en Chile, y obligar a "12500" es fricción sin motivo.
    const limpio = Number(String(monto).replace(/[.\s$]/g, ''))

    if (!Number.isInteger(limpio) || limpio <= 0) {
      setError('El monto tiene que ser un número entero de pesos, mayor que cero.')
      montoRef.current?.focus()
      return
    }

    setBusy(true)
    setError('')
    try {
      await onGuardar({
        amount: limpio,
        category_id: categoria,
        payment_method_id: medio,
        spent_on: fecha,
        description: descripcion.trim() || null,
      })
      setMonto('')
      setDescripcion('')
      setFecha(hoy())
      montoRef.current?.focus()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="gasto-form" onSubmit={enviar}>
      <div className="gasto-monto">
        <span className="signo">$</span>
        <input
          ref={montoRef}
          value={monto}
          onChange={(e) => setMonto(e.target.value)}
          // inputMode numérico: en el celular abre el teclado de números sin
          // impedir escribir el punto de miles.
          inputMode="numeric"
          placeholder="12.500"
          autoFocus
          aria-label="Monto en pesos"
        />
      </div>

      <div className="gasto-campo">
        <span className="etiqueta">Categoría</span>
        <div className="opciones">
          {categorias.map((c) => (
            <button
              type="button"
              key={c.id}
              aria-pressed={categoria === c.id}
              onClick={() => setCategoria(c.id)}
            >
              {c.name}
            </button>
          ))}
        </div>
      </div>

      <div className="gasto-campo">
        <span className="etiqueta">Medio de pago</span>
        <div className="opciones">
          {medios.map((m) => (
            <button
              type="button"
              key={m.id}
              aria-pressed={medio === m.id}
              onClick={() => setMedio(m.id)}
            >
              {m.name}
            </button>
          ))}
          <button
            type="button"
            className="gestionar-etiquetas"
            onClick={onGestionar}
            title="Categorías y medios de pago"
          >
            ⚙
          </button>
        </div>
      </div>

      <div className="gasto-extra">
        <input
          type="date"
          value={fecha}
          onChange={(e) => setFecha(e.target.value)}
          aria-label="Fecha del gasto"
        />
        <input
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
          placeholder="Descripción (opcional)"
          maxLength={300}
        />
        <button
          className="primary"
          disabled={busy || !monto || !categoria || !medio}
        >
          {busy ? 'Guardando…' : 'Registrar'}
        </button>
      </div>

      {error && <p className="gasto-error">{error}</p>}
    </form>
  )
}
