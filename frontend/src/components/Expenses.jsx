import { useCallback, useEffect, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'
import { PERIODOS, pesos, rango } from '../periodos.js'
import ExpenseForm from './ExpenseForm.jsx'
import LabelManager from './LabelManager.jsx'

function fechaCorta(iso) {
  // El texto llega como YYYY-MM-DD; se parte a mano en vez de usar Date para
  // que el navegador no lo interprete como UTC y lo corra un día.
  const [, mes, dia] = iso.split('-')
  return `${dia}/${mes}`
}

/**
 * Barras del desglose, ordenadas de mayor a menor por el backend.
 *
 * Las categorías con detalle se pueden abrir: el resumen se lee de un vistazo
 * y el detalle fino queda a un clic, en vez de 17 barras siempre visibles.
 */
function Desglose({ titulo, tajadas }) {
  const [abierta, setAbierta] = useState(null)

  if (tajadas.length === 0) return null

  return (
    <div className="desglose">
      <h3>{titulo}</h3>
      {tajadas.map((t) => {
        const tieneDetalle = (t.sub ?? []).length > 0
        const abiertaEsta = abierta === t.id

        return (
          <div className="tajada" key={t.id}>
            <div
              className={`tajada-texto ${tieneDetalle ? 'plegable' : ''}`}
              onClick={() => tieneDetalle && setAbierta(abiertaEsta ? null : t.id)}
              role={tieneDetalle ? 'button' : undefined}
              tabIndex={tieneDetalle ? 0 : undefined}
              onKeyDown={(e) => {
                if (tieneDetalle && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  setAbierta(abiertaEsta ? null : t.id)
                }
              }}
            >
              <span>
                {tieneDetalle && (
                  <span className={`flecha ${abiertaEsta ? 'abierta' : ''}`}>›</span>
                )}
                {t.name}
              </span>
              <span className="tajada-monto">
                {pesos(t.total)}
                <span className="tajada-pct">{t.porcentaje}%</span>
              </span>
            </div>
            <div className="barra">
              <div className="relleno-barra" style={{ width: `${t.porcentaje}%` }} />
            </div>

            {abiertaEsta &&
              t.sub.map((s) => (
                <div className="tajada hija" key={s.id}>
                  <div className="tajada-texto">
                    <span>{s.name}</span>
                    <span className="tajada-monto">
                      {pesos(s.total)}
                      <span className="tajada-pct">{s.porcentaje}%</span>
                    </span>
                  </div>
                  <div className="barra">
                    <div
                      className="relleno-barra"
                      style={{ width: `${s.porcentaje}%` }}
                    />
                  </div>
                </div>
              ))}
          </div>
        )
      })}
    </div>
  )
}

/** Serie de los últimos meses, para ver si este mes va más arriba o más abajo. */
function Meses({ meses }) {
  if (meses.length < 2) return null

  const tope = Math.max(...meses.map((m) => m.total)) || 1

  return (
    <div className="desglose">
      <h3>Últimos meses</h3>
      <div className="columnas">
        {meses.map((m, i) => (
          <div className="columna" key={m.mes}>
            <span className="columna-monto">{pesos(m.total)}</span>
            <div
              className={`columna-barra ${i === meses.length - 1 ? 'actual' : ''}`}
              style={{ height: `${Math.max((m.total / tope) * 100, 3)}%` }}
            />
            <span className="columna-mes">{m.mes.slice(5)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Expenses({ onUnauthorized, onError, borrador, onBorradorUsado }) {
  const [periodo, setPeriodo] = useState('mes')
  const [offset, setOffset] = useState(0)

  const [gastos, setGastos] = useState([])
  const [resumen, setResumen] = useState(null)
  const [categorias, setCategorias] = useState([])
  const [medios, setMedios] = useState([])
  const [loading, setLoading] = useState(true)
  const [gestionando, setGestionando] = useState(false)

  const { desde, hasta, etiqueta } = rango(periodo, offset)

  const manejarError = useCallback(
    (err) => {
      if (err instanceof UnauthorizedError) onUnauthorized()
      else onError(err.message)
    },
    [onUnauthorized, onError],
  )

  const cargarEtiquetas = useCallback(async () => {
    try {
      const [cs, ms] = await Promise.all([
        api.expenseCategories(),
        api.expenseMethods(),
      ])
      setCategorias(cs)
      setMedios(ms)
    } catch (err) {
      manejarError(err)
    }
  }, [manejarError])

  const cargar = useCallback(async () => {
    setLoading(true)
    try {
      const [lista, totales] = await Promise.all([
        api.expenses(desde, hasta),
        api.expenseSummary(desde, hasta),
      ])
      setGastos(lista)
      setResumen(totales)
    } catch (err) {
      manejarError(err)
    } finally {
      setLoading(false)
    }
  }, [desde, hasta, manejarError])

  useEffect(() => {
    cargarEtiquetas()
  }, [cargarEtiquetas])

  useEffect(() => {
    cargar()
  }, [cargar])

  async function registrar(datos) {
    await api.createExpense(datos)
    onBorradorUsado?.()
    await cargar()
  }

  async function eliminar(gasto) {
    if (!window.confirm(`¿Eliminar el gasto de ${pesos(gasto.amount)}?`)) return
    try {
      await api.deleteExpense(gasto.id)
      await cargar()
    } catch (err) {
      manejarError(err)
    }
  }

  return (
    <section className="gastos">
      <ExpenseForm
        categorias={categorias}
        medios={medios}
        descripcionInicial={borrador ?? ''}
        onGuardar={registrar}
        onGestionar={() => setGestionando(true)}
      />

      <div className="periodo">
        <div className="periodo-tipos">
          {PERIODOS.map((p) => (
            <button
              key={p.id}
              aria-pressed={periodo === p.id}
              onClick={() => {
                setPeriodo(p.id)
                // Cambiar de unidad vuelve al presente: quedarse tres semanas
                // atrás al pasar de semana a mes sería desconcertante.
                setOffset(0)
              }}
            >
              {p.label}
            </button>
          ))}
        </div>

        {periodo !== 'todo' && (
          <div className="periodo-nav">
            <button onClick={() => setOffset(offset - 1)} aria-label="Anterior">
              ‹
            </button>
            <span className="periodo-etiqueta">{etiqueta}</span>
            <button
              onClick={() => setOffset(offset + 1)}
              disabled={offset >= 0}
              aria-label="Siguiente"
            >
              ›
            </button>
          </div>
        )}
      </div>

      {resumen && (
        <div className="totales">
          <div className="total-grande">
            <span className="total-monto">{pesos(resumen.total)}</span>
            <span className="total-detalle">
              {resumen.cantidad} {resumen.cantidad === 1 ? 'gasto' : 'gastos'}
              {periodo !== 'todo' && ` · ${etiqueta}`}
            </span>
          </div>

          <Desglose titulo="Por categoría" tajadas={resumen.por_categoria} />
          <Desglose titulo="Por medio de pago" tajadas={resumen.por_medio} />
          <Meses meses={resumen.meses} />
        </div>
      )}

      <div className="lista-gastos">
        <h3>Movimientos</h3>
        {loading && gastos.length === 0 && <p className="cargando">Cargando…</p>}
        {!loading && gastos.length === 0 && (
          <p className="vacio">No hay gastos en este período.</p>
        )}
        {gastos.map((g) => (
          <div className="gasto" key={g.id}>
            <span className="gasto-fecha">{fechaCorta(g.spent_on)}</span>
            <span className="gasto-detalle">
              <strong>{g.category_name}</strong>
              <span className="gasto-sub"> › {g.subcategory_name}</span>
              {g.description && <span className="gasto-desc"> · {g.description}</span>}
              <span className="gasto-medio">{g.payment_method_name}</span>
            </span>
            <span className="gasto-valor">{pesos(g.amount)}</span>
            <button
              className="quitar"
              onClick={() => eliminar(g)}
              aria-label={`Eliminar gasto de ${pesos(g.amount)}`}
              title="Eliminar"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {gestionando && (
        <LabelManager
          categorias={categorias}
          medios={medios}
          onClose={() => setGestionando(false)}
          onChanged={async () => {
            await cargarEtiquetas()
            await cargar()
          }}
        />
      )}
    </section>
  )
}
