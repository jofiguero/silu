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

function ventanaDeUrl() {
  const primera = window.location.pathname.split('/')[1]
  return VENTANAS.includes(primera) ? primera : null
}

export function useVentana() {
  const [ventana, setVentana] = useState(() => ventanaDeUrl() ?? POR_DEFECTO)

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
