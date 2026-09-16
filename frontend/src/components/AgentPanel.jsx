import { useEffect, useRef, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'

const SUGERENCIAS = [
  'Archiva los gastos y déjalos como registrados',
  'Pasa a en curso lo de PowerQuery',
  '¿Qué tengo pendiente?',
]

export default function AgentPanel({ onChanged, onUnauthorized }) {
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  async function send(text) {
    const content = text.trim()
    if (!content || busy) return

    // El historial completo se manda en cada petición: el agente no guarda
    // estado, así que la conversación vive donde el usuario la ve.
    const next = [...messages, { role: 'user', content }]
    setMessages(next)
    setDraft('')
    setBusy(true)

    try {
      const result = await api.chat(next.filter((m) => m.role !== 'error'))
      setMessages([...next, { role: 'assistant', content: result.reply }])
      if (result.changed) onChanged()
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onUnauthorized()
        return
      }
      setMessages([...next, { role: 'error', content: err.message }])
    } finally {
      setBusy(false)
    }
  }

  function onKeyDown(event) {
    // Enter envía; Shift+Enter hace salto de línea. En el celular el teclado
    // manda un Enter normal, así que enviar es el comportamiento esperado.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send(draft)
    }
  }

  return (
    <>
      <div className="chat">
        {messages.length === 0 && (
          <div className="empty">
            <p>Pídeme que mueva, edite o archive tickets.</p>
            {SUGERENCIAS.map((s) => (
              <p key={s}>
                <button onClick={() => send(s)}>{s}</button>
              </p>
            ))}
          </div>
        )}

        {messages.map((message, index) => (
          <div key={index} className={`msg ${message.role}`}>
            {message.content}
          </div>
        ))}

        {busy && <div className="msg assistant">Pensando…</div>}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Archiva los gastos de esta semana…"
          rows={1}
        />
        <button
          className="primary"
          onClick={() => send(draft)}
          disabled={busy || !draft.trim()}
        >
          Enviar
        </button>
      </div>
    </>
  )
}
