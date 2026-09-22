/**
 * Aritmética de semanas, con el lunes como primer día.
 *
 * Las fechas se arman y se leen a mano en horario local: `toISOString()` pasa
 * por UTC y en Chile eso corre el día hacia atrás, que en un panel de tareas
 * diarias significa ver la tarea del lunes puesta el domingo.
 */

export const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

/** Date -> 'YYYY-MM-DD', sin pasar por UTC. */
export function iso(fecha) {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${fecha.getFullYear()}-${mes}-${dia}`
}

/** 'YYYY-MM-DD' -> Date local. */
export function desdeIso(texto) {
  const [a, m, d] = texto.split('-').map(Number)
  return new Date(a, m - 1, d)
}

export function lunesDe(fecha) {
  const copia = new Date(fecha)
  // getDay() devuelve 0 para domingo; con el lunes primero, el domingo es 6.
  const desplazamiento = (copia.getDay() + 6) % 7
  copia.setDate(copia.getDate() - desplazamiento)
  return copia
}

export function hoyIso() {
  return iso(new Date())
}

export function semanaActual() {
  return iso(lunesDe(new Date()))
}

/** Los siete días de la semana que empieza en `lunesIso`. */
export function diasDe(lunesIso) {
  const lunes = desdeIso(lunesIso)
  return DIAS.map((nombre, i) => {
    const fecha = new Date(lunes)
    fecha.setDate(lunes.getDate() + i)
    return { nombre, fecha: iso(fecha), numero: fecha.getDate() }
  })
}

export function sumarSemanas(lunesIso, cuantas) {
  const fecha = desdeIso(lunesIso)
  fecha.setDate(fecha.getDate() + cuantas * 7)
  return iso(fecha)
}

/** 'Semana del 22 de septiembre', o 'Esta semana' si es la actual. */
export function etiquetaSemana(lunesIso) {
  if (lunesIso === semanaActual()) return 'Esta semana'
  const fecha = desdeIso(lunesIso)
  return `Semana del ${fecha.toLocaleDateString('es-CL', {
    day: 'numeric',
    month: 'long',
  })}`
}

/** Etiqueta corta de un día: 'Hoy', 'Mañana' o 'Jueves 24'. */
export function etiquetaDia(diaIso) {
  if (diaIso === hoyIso()) return 'Hoy'
  const manana = new Date()
  manana.setDate(manana.getDate() + 1)
  if (diaIso === iso(manana)) return 'Mañana'
  const fecha = desdeIso(diaIso)
  return `${DIAS[(fecha.getDay() + 6) % 7]} ${fecha.getDate()}`
}
