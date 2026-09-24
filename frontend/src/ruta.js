import { useCallback, useEffect, useState } from 'react'

/**
 * La ventana abierta, guardada en la URL.
 *
 * Cuatro rutas planas y sin parámetros no justifican una librería de ruteo:
 * `history` y `popstate` alcanzan y son lo que esa librería usaría por dentro.
 *
 * Caddy sirve index.html para cualquier ruta que no sea /api, así que entrar
 * directo a /gastos o recargar ahí funciona igual que la raíz.
 */
export const VENTANAS = ['bandeja', 'tareas', 'gastos', 'prompts']

const POR_DEFECTO = 'bandeja'
const CLAVE = 'silu:ventana'

function ventanaDeUrl() {
  const primera = window.location.pathname.split('/')[1]
  return VENTANAS.includes(primera) ? primera : null
}

/**
 * La última ventana usada, para entrar por el dominio pelado.
 *
 * La URL manda siempre que diga algo: un enlace a /gastos abre gastos aunque
 * la última vez se haya estado en tareas. Esto es solo para la raíz, que es
 * lo que abre un marcador.
 *
 * En ventana privada o con el almacenamiento bloqueado esto lanza, así que va
 * envuelto: quedarse sin memoria de la última ventana no puede tumbar la app.
 */
function recordada() {
  try {
    const guardada = window.localStorage.getItem(CLAVE)
    return VENTANAS.includes(guardada) ? guardada : null
  } catch {
    return null
  }
}

export function useVentana() {
  const [ventana, setVentana] = useState(
    () => ventanaDeUrl() ?? recordada() ?? POR_DEFECTO,
  )

  useEffect(() => {
    try {
      window.localStorage.setItem(CLAVE, ventana)
    } catch {
      // Sin almacenamiento se pierde la memoria entre visitas, nada más.
    }
  }, [ventana])

  useEffect(() => {
    // Atrás y adelante del navegador mandan: la URL es la fuente de verdad,
    // el estado solo la sigue.
    const alVolver = () => setVentana(ventanaDeUrl() ?? POR_DEFECTO)
    window.addEventListener('popstate', alVolver)
    return () => window.removeEventListener('popstate', alVolver)
  }, [])

  useEffect(() => {
    // La raíz o una ruta que no existe se normaliza con replace y no con
    // push: el botón atrás no debe llevar de vuelta a una URL inválida.
    if (ventanaDeUrl() === null) {
      window.history.replaceState(null, '', `/${ventana}`)
    }
  }, [ventana])

  const ir = useCallback((nueva) => {
    setVentana((actual) => {
      if (nueva === actual) return actual
      window.history.pushState(null, '', `/${nueva}`)
      return nueva
    })
  }, [])

  return [ventana, ir]
}
