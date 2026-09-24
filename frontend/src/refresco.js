import { useEffect } from 'react'

/**
 * Vuelve a pedir los datos cada cierto rato, mientras se esté mirando.
 *
 * Es sondeo y no una conexión abierta a propósito. Lo que llega de afuera son
 * capturas del bot: un puñado al día, y que aparezcan medio minuto después no
 * cambia nada. Un WebSocket significaría estado en el servidor, reconexión y
 * un camino nuevo por donde puede fallar, a cambio de una latencia que aquí
 * no se nota.
 *
 * No corre con la pestaña en segundo plano: nadie está mirando, y el navegador
 * estrangula los temporizadores igual. Al volver a la pestaña refresca de
 * inmediato en vez de esperar el siguiente intervalo, que es el momento en que
 * de verdad importa estar al día.
 *
 * `activo` en false lo suspende. Sirve para no re-renderizar una lista con un
 * modal abierto encima o en medio de un arrastre, que lo cancelaría.
 */
export function useRefrescoPeriodico(refrescar, { intervalo = 20000, activo = true } = {}) {
  useEffect(() => {
    if (!activo) return undefined

    const siSeEstaViendo = () => {
      if (document.visibilityState === 'visible') refrescar()
    }

    const timer = setInterval(siSeEstaViendo, intervalo)
    document.addEventListener('visibilitychange', siSeEstaViendo)
    window.addEventListener('focus', siSeEstaViendo)

    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', siSeEstaViendo)
      window.removeEventListener('focus', siSeEstaViendo)
    }
  }, [refrescar, intervalo, activo])
}
