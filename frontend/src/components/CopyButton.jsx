import { useEffect, useState } from 'react'

/**
 * Copia texto al portapapeles y confirma que lo hizo.
 *
 * La confirmación no es decorativa: sin ella no hay forma de saber si el clic
 * funcionó, y uno termina copiando dos veces por las dudas.
 */
export default function CopyButton({ texto, etiqueta = 'Copiar', className = '' }) {
  const [copiado, setCopiado] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!copiado && !error) return
    const timer = setTimeout(() => {
      setCopiado(false)
      setError(false)
    }, 2000)
    return () => clearTimeout(timer)
  }, [copiado, error])

  async function copiar() {
    try {
      await navigator.clipboard.writeText(texto)
      setCopiado(true)
    } catch {
      // El portapapeles exige contexto seguro y permiso del navegador; si
      // falla, se avisa en vez de fingir que copió.
      setError(true)
    }
  }

  return (
    <button
      type="button"
      className={`copiar ${copiado ? 'copiado' : ''} ${className}`}
      onClick={copiar}
    >
      {copiado ? '✓ Copiado' : error ? 'No se pudo copiar' : etiqueta}
    </button>
  )
}
