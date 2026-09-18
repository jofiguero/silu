/**
 * El cerebro de Silu.
 *
 * Mismo dibujo que el favicon, en SVG en línea: así toma el color del contexto
 * y no depende de una petición extra para pintarse.
 */
export default function Logo({ size = 22 }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className="logo"
    >
      <rect width="32" height="32" rx="7" fill="currentColor" />
      <g fill="#fff">
        <circle cx="16" cy="12" r="4.6" />
        <circle cx="11" cy="13.6" r="4.4" />
        <circle cx="21" cy="13.6" r="4.4" />
        <circle cx="10.6" cy="18.4" r="4" />
        <circle cx="21.4" cy="18.4" r="4" />
        <circle cx="16" cy="18" r="4.8" />
        <circle cx="13.6" cy="22" r="3.1" />
        <circle cx="18.4" cy="22" r="3.1" />
      </g>
      {/* La cisura central es lo que lo vuelve un cerebro y no una nube. */}
      <path
        d="M16 8.2v15"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path
        d="M12.6 14.4c1.5.3 2.2 1.4 2 2.8M19.4 14.4c-1.5.3-2.2 1.4-2 2.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  )
}
