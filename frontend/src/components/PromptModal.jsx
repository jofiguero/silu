import { useEffect, useState } from 'react'

import CopyButton from './CopyButton.jsx'

function formatFull(iso) {
  return new Date(iso).toLocaleString('es-CL', {
    day: '2-digit',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * El prompt completo, con copiar y editar.
 *
 * Copiar es la acción principal —para eso existe la ventana— así que está
 * arriba y siempre visible, sin entrar a ningún modo.
 */
export default function PromptModal({
  prompt,
  proyectos,
  onClose,
  onGuardar,
  onMover,
  onEliminar,
  onError,
}) {
  const [editando, setEditando] = useState(false)
  const [titulo, setTitulo] = useState(prompt.title)
  const [contenido, setContenido] = useState(prompt.content)
  const [verOriginal, setVerOriginal] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    function onKey(event) {
      // Escape cierra, salvo mientras se edita: ahí perdería lo escrito.
      if (event.key === 'Escape' && !editando) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, editando])

  async function guardar() {
    setBusy(true)
    try {
      await onGuardar(prompt, { title: titulo.trim(), content: contenido })
      setEditando(false)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  function cancelar() {
    setTitulo(prompt.title)
    setContenido(prompt.content)
    setEditando(false)
  }

  return (
    <div className="overlay" onClick={editando ? undefined : onClose} role="presentation">
      <div
        className="modal prompt-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={prompt.title}
      >
        <div className="modal-head">
          {editando ? (
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              aria-label="Título"
            />
          ) : (
            <h2>{prompt.title}</h2>
          )}
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="prompt-barra">
          <CopyButton texto={prompt.content} etiqueta="Copiar prompt" className="primary" />

          {editando ? (
            <>
              <button onClick={cancelar} disabled={busy}>
                Cancelar
              </button>
              <button className="primary" onClick={guardar} disabled={busy}>
                {busy ? 'Guardando…' : 'Guardar'}
              </button>
            </>
          ) : (
            <button onClick={() => setEditando(true)}>Editar</button>
          )}

          <span style={{ flex: 1 }} />

          <select
            value={prompt.project_id ?? ''}
            onChange={(e) => onMover(prompt, e.target.value || null)}
            aria-label="Proyecto"
            disabled={editando}
          >
            <option value="">Sin proyecto</option>
            {proyectos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

        {editando ? (
          <textarea
            className="prompt-editor"
            value={contenido}
            onChange={(e) => setContenido(e.target.value)}
            aria-label="Contenido del prompt"
          />
        ) : (
          // pre y no Markdown renderizado: lo que se ve tiene que ser
          // exactamente lo que se copia, sin formato que se pierda al pegar.
          <pre className="prompt-texto">{prompt.content}</pre>
        )}

        <div className="prompt-pie">
          <span>
            {formatFull(prompt.created_at)}
            {prompt.edited && ' · editado a mano'}
          </span>
          <button className="ghost" onClick={() => setVerOriginal(!verOriginal)}>
            {verOriginal ? 'Ocultar original' : 'Ver lo que dicté'}
          </button>
          <button
            className="danger"
            onClick={() => onEliminar(prompt)}
            disabled={busy}
          >
            Eliminar
          </button>
        </div>

        {verOriginal && (
          <div className="campo">
            <dt>Transcripción original</dt>
            <dd className="original">{prompt.raw_text}</dd>
          </div>
        )}
      </div>
    </div>
  )
}
