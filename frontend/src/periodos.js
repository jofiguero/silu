/**
 * Rangos de fecha del panel de gastos.
 *
 * Todo se calcula en la zona horaria del navegador y se manda como texto
 * `YYYY-MM-DD`: el servidor corre en UTC y "hoy" en Chile no siempre coincide
 * con el día del servidor.
 */

export const PERIODOS = [
  { id: 'dia', label: 'Día' },
  { id: 'semana', label: 'Semana' },
  { id: 'mes', label: 'Mes' },
  { id: 'todo', label: 'Todo' },
]

export function aTexto(fecha) {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${fecha.getFullYear()}-${mes}-${dia}`
}

export function hoy() {
  return aTexto(new Date())
}

/**
 * Calcula el rango de un período, desplazado `offset` unidades hacia atrás.
 * offset 0 es el período actual, -1 el anterior, +1 el siguiente.
 */
export function rango(periodo, offset = 0) {
  const base = new Date()
  base.setHours(12, 0, 0, 0) // mediodía: evita saltos por horario de verano

  if (periodo === 'dia') {
    base.setDate(base.getDate() + offset)
    return { desde: aTexto(base), hasta: aTexto(base), etiqueta: etiquetaDia(base) }
  }

  if (periodo === 'semana') {
    base.setDate(base.getDate() + offset * 7)
    // Semana de lunes a domingo: getDay() devuelve 0 para domingo.
    const dia = (base.getDay() + 6) % 7
    const lunes = new Date(base)
    lunes.setDate(base.getDate() - dia)
    const domingo = new Date(lunes)
    domingo.setDate(lunes.getDate() + 6)
    return {
      desde: aTexto(lunes),
      hasta: aTexto(domingo),
      etiqueta: `${lunes.getDate()} – ${domingo.getDate()} ${mesCorto(domingo)}`,
    }
  }

  if (periodo === 'mes') {
    const primero = new Date(base.getFullYear(), base.getMonth() + offset, 1, 12)
    // Día 0 del mes siguiente es el último del actual, sin tablas de días.
    const ultimo = new Date(primero.getFullYear(), primero.getMonth() + 1, 0, 12)
    return {
      desde: aTexto(primero),
      hasta: aTexto(ultimo),
      etiqueta: `${mesLargo(primero)} ${primero.getFullYear()}`,
    }
  }

  // Todo: un rango lo bastante amplio como para no dejar nada fuera.
  return { desde: '2000-01-01', hasta: '2100-12-31', etiqueta: 'Todo' }
}

function mesCorto(fecha) {
  return fecha.toLocaleDateString('es-CL', { month: 'short' })
}

function mesLargo(fecha) {
  return fecha.toLocaleDateString('es-CL', { month: 'long' })
}

function etiquetaDia(fecha) {
  const texto = fecha.toLocaleDateString('es-CL', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

/** 4500 -> "$4.500". Sin decimales: el peso chileno no tiene centavos. */
export function pesos(monto) {
  return `$${Number(monto).toLocaleString('es-CL', { maximumFractionDigits: 0 })}`
}
