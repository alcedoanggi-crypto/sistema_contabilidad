import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

export function Titulo({ titulo, subtitulo, children }) {
  return (
    <div className="no-imprimir mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-tinta-900">{titulo}</h1>
        {subtitulo && <p className="mt-0.5 text-sm text-tinta-400">{subtitulo}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  )
}

export function Aviso({ tipo = 'error', children }) {
  if (!children) return null
  const estilos = { error: 'border-red-200 bg-red-50 text-red-800', ok: 'border-menta-100 bg-menta-50 text-menta-700', info: 'border-tinta-200 bg-tinta-50 text-tinta-700' }
  return <div className={`mb-4 rounded-lg border px-4 py-2.5 text-sm ${estilos[tipo]}`}>{children}</div>
}

const coloresEstado = {
  borrador: 'bg-amber-100 text-amber-800', contabilizada: 'bg-menta-100 text-menta-700', cancelada: 'bg-red-100 text-red-700',
  vigente: 'bg-sky-100 text-sky-800', pagada: 'bg-menta-100 text-menta-700', abierto: 'bg-sky-100 text-sky-800', cerrado: 'bg-tinta-100 text-tinta-700',
}
export const Estado = ({ valor }) => <span className={`pastilla ${coloresEstado[valor] || 'bg-tinta-100 text-tinta-700'}`}>{valor}</span>

export function Cargando({ children = 'Cargando…' }) {
  return <div className="py-16 text-center text-sm text-tinta-400">{children}</div>
}

// Hook sencillo para cargar datos de la API
export function useApi(ruta, deps = []) {
  const [estado, setEstado] = useState({ datos: null, error: '', cargando: true })
  const recargar = () => {
    if (!ruta) return
    setEstado((e) => ({ ...e, cargando: true }))
    api(ruta).then((datos) => setEstado({ datos, error: '', cargando: false }))
      .catch((e) => setEstado({ datos: null, error: e.message, cargando: false }))
  }
  useEffect(recargar, [ruta, ...deps])
  return { ...estado, recargar }
}

// Selector de cuentas con búsqueda por código o nombre (solo cuentas de detalle)
export function SelectorCuenta({ valor, onCambio, tipo, autoFocus, onEnter }) {
  const [texto, setTexto] = useState(valor ? `${valor.codigo} ${valor.nombre}` : '')
  const [opciones, setOpciones] = useState([])
  const [abierto, setAbierto] = useState(false)
  const [activo, setActivo] = useState(0)
  const ultima = useRef(0)   // cada letra lanza una búsqueda: solo vale la respuesta de la más reciente

  useEffect(() => { setTexto(valor ? `${valor.codigo} ${valor.nombre}` : '') }, [valor?.id])

  const buscar = (q) => {
    setTexto(q)
    setAbierto(true)
    const n = ++ultima.current
    api(`/cuentas/buscar?q=${encodeURIComponent(q)}${tipo ? `&tipo=${tipo}` : ''}`)
      .then((r) => { if (n === ultima.current) { setOpciones(r); setActivo(0) } })
  }
  const elegir = (c) => { onCambio(c); setTexto(`${c.codigo} ${c.nombre}`); setAbierto(false); onEnter?.() }

  return (
    <div className="relative">
      <input className="campo" value={texto} autoFocus={autoFocus} placeholder="Código o nombre…"
        onFocus={() => buscar(valor ? '' : texto)} onChange={(e) => buscar(e.target.value)}
        onBlur={() => setTimeout(() => setAbierto(false), 150)}
        onKeyDown={(e) => {
          if (!abierto || !opciones.length) return
          if (e.key === 'ArrowDown') { e.preventDefault(); setActivo((a) => Math.min(a + 1, opciones.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setActivo((a) => Math.max(a - 1, 0)) }
          if (e.key === 'Enter') { e.preventDefault(); elegir(opciones[activo]) }
        }} />
      {abierto && opciones.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-tinta-100 bg-white py-1 shadow-lg">
          {opciones.map((c, i) => (
            <li key={c.id} onMouseDown={() => elegir(c)}
              className={`cursor-pointer px-3 py-1.5 text-sm ${i === activo ? 'bg-tinta-50' : ''}`}>
              <span className="font-mono text-tinta-400">{c.codigo}</span> {c.nombre}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
