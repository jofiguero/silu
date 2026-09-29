import { useCallback, useEffect, useRef, useState } from 'react'

import { api, UnauthorizedError } from '../api.js'
import { useCierreExterior } from '../cierre.js'
import CopyButton from './CopyButton.jsx'

// En el orden de la grilla: arriba lo que se iba a conversar y lo que se
// conversó, abajo lo que quedó pendiente y lo que se anotó al pasar.
const CUADRANTES = [
  {
    zona: 'temas',
    titulo: 'Por conversar',
    nota: 'Se llena antes de la reunión',
    placeholder: '+ Tema',
  },
  {
    zona: 'conversado',
    titulo: 'Conversado',
    nota: 'Arrastra aquí o marca ✓',
    placeholder: '+ Algo que se conversó',
  },
  {
    zona: 'tareas',
    titulo: 'Tareas pendientes',
    nota: 'Lo que quedó por hacer',
    placeholder: '+ Tarea',
  },
  {
    zona: 'apuntes',
    titulo: 'Apuntes',
    nota: 'Datos y acuerdos al pasar',
    placeholder: '+ Apunte',
  },
]

function Item({ item, onMover, onEditar, onEliminar, onArrastrar }) {
  const [editando, setEditando] = useState(false)
  const [texto, setTexto] = useState(item.text)

  function terminar() {
    setEditando(false)
    const limpio = texto.trim()
    // Vaciarlo no lo borra: borrar es la ×. Un texto vacío por accidente
    // perdería lo anotado sin aviso.
    if (!limpio || limpio === item.text) {
      setTexto(item.text)
      return
    }
    onEditar(item, limpio)
  }

  return (
    <li
      className={`item-reunion ${item.zona}`}
      draggable={!editando}
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', item.id)
        e.dataTransfer.effectAllowed = 'move'
        onArrastrar(item)
      }}
    >
      {/* El ✓ es el camino táctil: en el celular no hay arrastre. En lo
          conversado, el mismo botón lo devuelve si se marcó por error. */}
      {item.zona === 'temas' && (
        <button
          className="marca"
          onClick={() => onMover(item, 'conversado')}
          title="Ya se conversó"
          aria-label={`Marcar como conversado: ${item.text}`}
        >
          ✓
        </button>
      )}
      {item.zona === 'conversado' && (
        <button
          className="marca hecha"
          onClick={() => onMover(item, 'temas')}
          title="Volver a por conversar"
          aria-label={`Devolver a por conversar: ${item.text}`}
        >
          ✓
        </button>
      )}

      {editando ? (
        <input
          className="editar-item"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onBlur={terminar}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur()
            if (e.key === 'Escape') {
              setTexto(item.text)
              setEditando(false)
            }
          }}
          maxLength={2000}
          autoFocus
        />
      ) : (
        <button
          className="texto-item"
          onClick={() => setEditando(true)}
          title="Editar"
        >
          {item.text}
        </button>
      )}

      <button
        className="quitar"
        onClick={() => onEliminar(item)}
        aria-label={`Eliminar ${item.text}`}
        title="Eliminar"
      >
        ×
      </button>
    </li>
  )
}

function Cuadrante({ def, items, encima, onEncima, onSoltar, onAgregar, ...item }) {
  const [nuevo, setNuevo] = useState('')

  async function agregar(event) {
    event.preventDefault()
    const texto = nuevo.trim()
    if (!texto) return
    // Se limpia antes de que responda el servidor: en plena reunión se anota
    // una cosa tras otra y el campo no puede quedar trabado esperando.
    setNuevo('')
    const ok = await onAgregar(def.zona, texto)
    if (!ok) setNuevo(texto)
  }

  return (
    <section
      className={`cuadrante ${def.zona} ${encima ? 'encima' : ''}`}
      onDragOver={(e) => {
        // Sin preventDefault el navegador no acepta soltar aquí.
        e.preventDefault()
        onEncima(def.zona)
      }}
      onDrop={(e) => {
        e.preventDefault()
        onSoltar(def.zona)
      }}
    >
      <header>
        <h3>{def.titulo}</h3>
        <span className="nota">{def.nota}</span>
        <span className="zona-cuenta">{items.length || ''}</span>
      </header>

      <ul className="items-reunion">
        {items.map((i) => (
          <Item key={i.id} item={i} {...item} />
        ))}
      </ul>

      <form className="nuevo-item" onSubmit={agregar}>
        <input
          value={nuevo}
          onChange={(e) => setNuevo(e.target.value)}
          placeholder={def.placeholder}
          maxLength={2000}
        />
      </form>
    </section>
  )
}

function Resumen({ reunion, onClose }) {
  return (
    <div className="overlay" {...useCierreExterior(onClose)}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`Resumen de ${reunion.title}`}
      >
        <div className="modal-head">
          <h2>Resumen</h2>
          <button className="cerrar" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>
        <div className="resumen-texto">{reunion.summary}</div>
        <div className="acciones-modal">
          <span className="nota">
            {new Date(reunion.summary_at).toLocaleString('es-CL', {
              day: 'numeric',
              month: 'short',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
          <span style={{ flex: 1 }} />
          <CopyButton texto={reunion.summary} />
        </div>
      </div>
    </div>
  )
}

/**
 * Una reunión abierta: cuatro cuadrantes a pantalla completa.
 *
 * No hay botón de guardar. Cada cosa se guarda al escribirla o moverla: si se
 * cierra la pestaña o se corta la red a mitad de la reunión, lo anotado hasta
 * ahí ya está en la base.
 */
export default function MeetingBoard({ id, onVolver, onUnauthorized, onError }) {
  const [reunion, setReunion] = useState(null)
  const [titulo, setTitulo] = useState('')
  const [encima, setEncima] = useState(null)
  const [resumiendo, setResumiendo] = useState(false)
  const [verResumen, setVerResumen] = useState(false)
  const arrastrado = useRef(null)

  const manejarError = useCallback(
    (err) => {
      if (err instanceof UnauthorizedError) onUnauthorized()
      else onError(err.message)
    },
    [onUnauthorized, onError],
  )

  const cargar = useCallback(async () => {
    try {
      const datos = await api.meeting(id)
      setReunion(datos)
      setTitulo(datos.title)
    } catch (err) {
      manejarError(err)
      // Borrada, ajena o un enlace viejo: no hay tablero que mostrar.
      if (!(err instanceof UnauthorizedError)) onVolver(null)
    }
  }, [id, manejarError, onVolver])

  useEffect(() => {
    cargar()
  }, [cargar])

  function cambiarItems(transformar) {
    setReunion((r) => ({ ...r, items: transformar(r.items) }))
  }

  async function agregar(zona, texto) {
    try {
      const item = await api.addMeetingItem(id, zona, texto)
      cambiarItems((items) => [...items, item])
      return true
    } catch (err) {
      manejarError(err)
      return false
    }
  }

  async function mover(item, zona) {
    if (!item || item.zona === zona) return
    // Se pinta al tiro al final del cuadrante de destino, que es donde lo
    // deja el servidor: soltar algo y verlo saltar después se siente roto.
    cambiarItems((items) => {
      const ultima = Math.max(
        -1,
        ...items.filter((i) => i.zona === zona).map((i) => i.position),
      )
      return items.map((i) =>
        i.id === item.id ? { ...i, zona, position: ultima + 1 } : i,
      )
    })
    try {
      const movido = await api.updateMeetingItem(item.id, { zona })
      cambiarItems((items) => items.map((i) => (i.id === movido.id ? movido : i)))
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  async function editar(item, text) {
    cambiarItems((items) => items.map((i) => (i.id === item.id ? { ...i, text } : i)))
    try {
      await api.updateMeetingItem(item.id, { text })
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  async function eliminar(item) {
    cambiarItems((items) => items.filter((i) => i.id !== item.id))
    try {
      await api.deleteMeetingItem(item.id)
    } catch (err) {
      manejarError(err)
      cargar()
    }
  }

  async function guardarEncabezado(cambios) {
    try {
      const actualizada = await api.updateMeeting(id, cambios)
      setReunion((r) => ({ ...r, title: actualizada.title, fecha: actualizada.fecha }))
      setTitulo(actualizada.title)
    } catch (err) {
      manejarError(err)
      setTitulo(reunion.title)
    }
  }

  async function resumir() {
    if (
      reunion.summary &&
      !window.confirm('Se reemplaza el resumen actual por uno nuevo. ¿Seguir?')
    )
      return
    setResumiendo(true)
    try {
      setReunion(await api.summarizeMeeting(id))
      setVerResumen(true)
    } catch (err) {
      manejarError(err)
    } finally {
      setResumiendo(false)
    }
  }

  async function eliminarReunion() {
    if (!window.confirm(`¿Eliminar "${reunion.title}" con todo lo anotado?`)) return
    try {
      await api.deleteMeeting(id)
      onVolver(reunion.folder_id)
    } catch (err) {
      manejarError(err)
    }
  }

  if (!reunion) return <p className="cargando">Cargando…</p>

  const deZona = (zona) =>
    reunion.items
      .filter((i) => i.zona === zona)
      .sort((a, b) => a.position - b.position)

  return (
    <section
      className="tablero-reunion"
      onDragEnd={() => {
        arrastrado.current = null
        setEncima(null)
      }}
    >
      <div className="tablero-barra">
        <button className="ghost volver" onClick={() => onVolver(reunion.folder_id)}>
          ← {reunion.folder_name}
        </button>
        <input
          className="titulo-reunion"
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          onBlur={() => {
            const limpio = titulo.trim()
            if (!limpio) setTitulo(reunion.title)
            else if (limpio !== reunion.title) guardarEncabezado({ title: limpio })
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur()
          }}
          maxLength={120}
          aria-label="Título de la reunión"
        />
        <input
          type="date"
          className="fecha-reunion"
          value={reunion.fecha}
          onChange={(e) => e.target.value && guardarEncabezado({ fecha: e.target.value })}
          aria-label="Fecha de la reunión"
        />
        <span style={{ flex: 1 }} />
        {reunion.summary && (
          <button onClick={() => setVerResumen(true)}>Ver resumen</button>
        )}
        <button className="primary" onClick={resumir} disabled={resumiendo}>
          {resumiendo
            ? 'Resumiendo…'
            : reunion.summary
              ? 'Regenerar resumen'
              : 'Generar resumen'}
        </button>
        <button
          className="ghost quitar-reunion"
          onClick={eliminarReunion}
          title="Eliminar reunión"
          aria-label="Eliminar reunión"
        >
          🗑
        </button>
      </div>

      <div className="cuadrantes">
        {CUADRANTES.map((def) => (
          <Cuadrante
            key={def.zona}
            def={def}
            items={deZona(def.zona)}
            encima={encima === def.zona}
            // Solo se escribe si cambió: dragover dispara decenas de veces
            // por segundo y re-renderizar en cada una cancela el arrastre.
            onEncima={(zona) => setEncima((actual) => (actual === zona ? actual : zona))}
            onSoltar={(zona) => {
              const item = arrastrado.current
              arrastrado.current = null
              setEncima(null)
              mover(item, zona)
            }}
            onAgregar={agregar}
            onMover={mover}
            onEditar={editar}
            onEliminar={eliminar}
            onArrastrar={(item) => {
              arrastrado.current = item
            }}
          />
        ))}
      </div>

      {verResumen && reunion.summary && (
        <Resumen reunion={reunion} onClose={() => setVerResumen(false)} />
      )}
    </section>
  )
}
