import { useRef } from 'react'

/**
 * Cerrar un modal al hacer clic fuera, sin que un arrastre lo cierre.
 *
 * Un `click` se dispara en el ancestro común del `mousedown` y el `mouseup`.
 * Al subrayar un texto del modal y soltar el botón afuera, ese ancestro es el
 * fondo, así que el modal se cerraba en medio de una selección y se perdía lo
 * que se estaba copiando.
 *
 * Por eso se exige que el gesto empiece Y termine en el fondo: un clic
 * deliberado afuera cierra; arrastrar desde adentro hacia afuera, no.
 *
 * Devuelve los props que van en el elemento del fondo. `onClose` puede venir
 * sin definir para bloquear el cierre (por ejemplo, con cambios sin guardar).
 */
export function useCierreExterior(onClose) {
  const empezoAfuera = useRef(false)

  return {
    onMouseDown: (event) => {
      // currentTarget es el fondo; target es lo que se presionó. Si son el
      // mismo, el gesto empezó en el fondo y no dentro del modal.
      empezoAfuera.current = event.target === event.currentTarget
    },
    onClick: (event) => {
      const terminoAfuera = event.target === event.currentTarget
      if (terminoAfuera && empezoAfuera.current) onClose?.()
      empezoAfuera.current = false
    },
    role: 'presentation',
  }
}
