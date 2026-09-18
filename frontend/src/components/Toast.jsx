import { useEffect } from 'react'

/** Aviso efímero con opción de deshacer. */
export default function Toast({ texto, onDeshacer, onCerrar, segundos = 6 }) {
  useEffect(() => {
    // Se cierra solo: si no vas a deshacer, no tiene por qué seguir ahí.
    const timer = setTimeout(onCerrar, segundos * 1000)
    return () => clearTimeout(timer)
  }, [onCerrar, segundos, texto])

  return (
    <div className="toast" role="status">
      <span>{texto}</span>
      <button onClick={onDeshacer}>Deshacer</button>
    </div>
  )
}
