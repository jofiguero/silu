import { useState } from 'react'

import { api } from '../api.js'
import { useCierreExterior } from '../cierre.js'

/**
 * La cuenta: quién eres y tu vínculo con Telegram.
 *
 * El código es lo que prueba que la misma persona controla las dos cuentas.
 * Se pide aquí, con sesión iniciada, y se dicta al bot desde el Telegram que
 * se quiere vincular.
 */
export default function AccountModal({ sesion, onClose, onCambio, onError }) {
  const [codigo, setCodigo] = useState(null)
  const [busy, setBusy] = useState(false)

  async function pedirCodigo() {
    setBusy(true)
    try {
      setCodigo(await api.codigoTelegram())
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function desvincular() {
    if (!window.confirm('¿Desvincular Telegram? El bot dejará de escribirte.'))
      return
    setBusy(true)
    try {
      onCambio(await api.desvincularTelegram())
      setCodigo(null)
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" {...useCierreExterior(onClose)}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Tu cuenta"
      >
        <div className="modal-head">
          <h2>Tu cuenta</h2>
          <span style={{ flex: 1 }} />
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>

        <div className="campos">
          <div className="campo">
            <dt>Correo</dt>
            <dd>{sesion.email}</dd>
          </div>

          <div className="campo">
            <dt>Rol</dt>
            <dd>
              <span className={`badge ${sesion.role === 'admin' ? 'urgente' : ''}`}>
                {sesion.role}
              </span>
            </dd>
          </div>

          <div className="campo">
            <dt>Telegram</dt>
            <dd>
              {sesion.telegram_vinculado ? (
                <div className="vinculo">
                  <span className="badge en_curso">vinculado</span>
                  <p className="nota">
                    Los audios que le mandes a los bots llegan a esta cuenta.
                  </p>
                  <button className="danger" onClick={desvincular} disabled={busy}>
                    Desvincular
                  </button>
                </div>
              ) : codigo ? (
                <div className="vinculo">
                  <p className="nota">
                    Mándale esto a cualquiera de los dos bots, desde el Telegram
                    que quieras vincular:
                  </p>
                  <code className="codigo-vinculo">/vincular {codigo.codigo}</code>
                  <p className="nota">
                    Vence en {codigo.expira_en_minutos} minutos y sirve una sola
                    vez. Después recarga esta página.
                  </p>
                </div>
              ) : (
                <div className="vinculo">
                  <p className="nota">
                    Sin vincular. Los bots no van a procesar lo que les mandes
                    hasta que lo hagas: sin saber de quién es un audio, no hay
                    bandeja a la que mandarlo.
                  </p>
                  <button className="primary" onClick={pedirCodigo} disabled={busy}>
                    {busy ? 'Pidiendo…' : 'Generar código'}
                  </button>
                </div>
              )}
            </dd>
          </div>
        </div>
      </div>
    </div>
  )
}
