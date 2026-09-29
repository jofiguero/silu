import { useCallback, useEffect, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'
import { desdeIso } from '../semana.js'
import MeetingBoard from './MeetingBoard.jsx'
import MeetingFolderForm from './MeetingFolderForm.jsx'

const CLAVE_CARPETA = 'silu:carpeta-reuniones'

/** La reunión abierta, si la URL es /reuniones/<id>. */
function reunionDeUrl() {
  const [, ventana, id] = window.location.pathname.split('/')
  return ventana === 'reuniones' && id ? id : null
}

// La última carpeta mirada, para volver a ella. Envuelto como en ruta.js: sin
// almacenamiento se pierde la memoria, no la ventana.
function carpetaRecordada() {
  try {
    return window.localStorage.getItem(CLAVE_CARPETA)
  } catch {
    return null
  }
}

function fechaReunion(iso) {
  // desdeIso y no new Date(iso): el texto sin hora se leería como medianoche
  // UTC, que en Chile es el día anterior.
  return desdeIso(iso).toLocaleDateString('es-CL', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export default function Meetings({ onUnauthorized, onError }) {
  // La reunión abierta vive en la URL: recargar a mitad de la reunión tiene
  // que dejar donde se estaba.
  const [reunionId, setReunionId] = useState(reunionDeUrl)
  const [carpetas, setCarpetas] = useState([])
  const [activa, setActiva] = useState(carpetaRecordada)
  const [reuniones, setReuniones] = useState([])
  const [cargando, setCargando] = useState(true)
  const [editando, setEditando] = useState(null) // carpeta | 'nueva' | null
  const [creando, setCreando] = useState(false)

  const manejarError = useCallback(
    (err) => {
      if (err instanceof UnauthorizedError) onUnauthorized()
      else onError(err.message)
    },
    [onUnauthorized, onError],
  )

  useEffect(() => {
    const alVolver = () => setReunionId(reunionDeUrl())
    window.addEventListener('popstate', alVolver)
    return () => window.removeEventListener('popstate', alVolver)
  }, [])

  useEffect(() => {
    try {
      if (activa) window.localStorage.setItem(CLAVE_CARPETA, activa)
    } catch {
      // Sin almacenamiento solo se pierde la memoria entre visitas.
    }
  }, [activa])

  const abrir = useCallback((id) => {
    window.history.pushState(null, '', `/reuniones/${id}`)
    setReunionId(id)
  }, [])

  const volver = useCallback((carpetaId) => {
    // Se vuelve a la carpeta de la reunión, que no tiene por qué ser la
    // última mirada: la reunión pudo abrirse desde un enlace.
    if (carpetaId) setActiva(carpetaId)
    window.history.pushState(null, '', '/reuniones')
    setReunionId(null)
  }, [])

  const cargarCarpetas = useCallback(async () => {
    try {
      const lista = await api.meetingFolders()
      setCarpetas(lista)
      // Si la recordada ya no existe (se borró, o es de otra cuenta en este
      // navegador), se cae a la primera.
      setActiva((a) => (lista.some((c) => c.id === a) ? a : (lista[0]?.id ?? null)))
    } catch (err) {
      manejarError(err)
    } finally {
      setCargando(false)
    }
  }, [manejarError])

  // Al volver de una reunión también: los contadores pudieron cambiar.
  useEffect(() => {
    if (!reunionId) cargarCarpetas()
  }, [reunionId, cargarCarpetas])

  useEffect(() => {
    if (reunionId || !activa || !carpetas.some((c) => c.id === activa)) return
    api.meetings(activa).then(setReuniones).catch(manejarError)
  }, [reunionId, activa, carpetas, manejarError])

  async function nuevaReunion() {
    setCreando(true)
    try {
      // Nace con la fecha de hoy y su título por defecto: crear una reunión
      // es un clic, y ambos se cambian arriba del tablero.
      const creada = await api.createMeeting({ folder_id: activa })
      abrir(creada.id)
    } catch (err) {
      manejarError(err)
    } finally {
      setCreando(false)
    }
  }

  async function guardarCarpeta(nombre) {
    if (editando === 'nueva') {
      const creada = await api.createMeetingFolder(nombre)
      setActiva(creada.id)
    } else {
      await api.updateMeetingFolder(editando.id, { name: nombre })
    }
    setEditando(null)
    await cargarCarpetas()
  }

  async function eliminarCarpeta(carpeta) {
    await api.deleteMeetingFolder(carpeta.id)
    setEditando(null)
    setReuniones([])
    await cargarCarpetas()
  }

  if (reunionId) {
    return (
      <MeetingBoard
        key={reunionId}
        id={reunionId}
        onVolver={volver}
        onUnauthorized={onUnauthorized}
        onError={onError}
      />
    )
  }

  const carpetaActiva = carpetas.find((c) => c.id === activa)

  return (
    <section className="reuniones">
      <div className="reuniones-barra">
        <nav className="carpetas">
          {carpetas.map((c) => (
            <button
              key={c.id}
              aria-pressed={activa === c.id}
              onClick={() => setActiva(c.id)}
            >
              {c.name}
              {c.meetings_count > 0 && <span className="count">{c.meetings_count}</span>}
            </button>
          ))}
        </nav>

        <div className="reuniones-acciones">
          {carpetaActiva && (
            <button
              onClick={() => setEditando(carpetaActiva)}
              title="Renombrar o eliminar la carpeta"
              aria-label="Editar carpeta"
            >
              ⚙
            </button>
          )}
          <button onClick={() => setEditando('nueva')}>+ Carpeta</button>
          {carpetaActiva && (
            <button className="primary" onClick={nuevaReunion} disabled={creando}>
              + Reunión
            </button>
          )}
        </div>
      </div>

      {cargando ? (
        <p className="cargando">Cargando…</p>
      ) : carpetas.length === 0 ? (
        <p className="vacio">
          Todavía no hay carpetas. Crea la primera con “+ Carpeta”, por ejemplo
          “Reuniones con Leonardo”.
        </p>
      ) : reuniones.length === 0 ? (
        <p className="vacio">Nada en esta carpeta todavía. Crea una con “+ Reunión”.</p>
      ) : (
        <ul className="lista-reuniones">
          {reuniones.map((r) => (
            <li key={r.id}>
              <button className="fila-reunion" onClick={() => abrir(r.id)}>
                <span className="titulo">{r.title}</span>
                <span className="fecha">{fechaReunion(r.fecha)}</span>
                {r.tiene_resumen && <span className="badge en_curso">resumen</span>}
              </button>
            </li>
          ))}
        </ul>
      )}

      {editando && (
        <MeetingFolderForm
          carpeta={editando === 'nueva' ? null : editando}
          onGuardar={guardarCarpeta}
          onEliminar={eliminarCarpeta}
          onClose={() => setEditando(null)}
        />
      )}
    </section>
  )
}
