import { useState } from 'react'
import { api } from '../api'
import { Aviso, Cargando, Titulo, useApi } from '../componentes/ui'

const colores = { activo: 'bg-sky-100 text-sky-800', pasivo: 'bg-amber-100 text-amber-800', capital: 'bg-violet-100 text-violet-800',
  ingreso: 'bg-menta-100 text-menta-700', gasto: 'bg-red-100 text-red-700' }

export default function Cuentas() {
  const { datos, error, cargando, recargar } = useApi('/cuentas')
  const [nueva, setNueva] = useState(null)
  const [msg, setMsg] = useState('')

  const guardar = async () => {
    setMsg('')
    try { await api('/cuentas', { metodo: 'POST', datos: nueva }); setNueva(null); recargar() }
    catch (e) { setMsg(e.message) }
  }
  if (cargando) return <Cargando />

  return (
    <>
      <Titulo titulo="Catálogo de cuentas" subtitulo="Jerárquico: las cuentas con subcuentas son de mayor y no aceptan movimientos">
        <button className="btn-primario" onClick={() => setNueva({ codigo: '', nombre: '', padre_id: null, tipo: 'activo' })}>+ Nueva cuenta</button>
      </Titulo>
      <Aviso>{error || msg}</Aviso>
      {nueva && (
        <div className="tarjeta mb-4 grid gap-3 p-4 md:grid-cols-[1.3fr_120px_1fr_auto]">
          <div><label className="etiqueta">Cuenta padre</label>
            <select className="campo" value={nueva.padre_id || ''} onChange={(e) => {
              const padre = datos.find((c) => c.id === Number(e.target.value))
              const hijos = datos.filter((c) => c.padre_id === padre?.id).length
              setNueva({ ...nueva, padre_id: padre?.id || null, codigo: padre ? `${padre.codigo}.${String(hijos + 1).padStart(padre.nivel >= 2 ? 2 : 1, '0')}` : '' })
            }}>
              <option value="">(Primer nivel)</option>
              {datos.filter((c) => !c.tiene_movimientos).map((c) => <option key={c.id} value={c.id}>{c.codigo} {c.nombre}</option>)}
            </select></div>
          <div><label className="etiqueta">Código</label><input className="campo font-mono" value={nueva.codigo} onChange={(e) => setNueva({ ...nueva, codigo: e.target.value })} /></div>
          <div><label className="etiqueta">Nombre</label><input className="campo" autoFocus value={nueva.nombre} onChange={(e) => setNueva({ ...nueva, nombre: e.target.value })} /></div>
          <div className="flex items-end gap-2"><button className="btn-borde" onClick={() => setNueva(null)}>Cerrar</button><button className="btn-verde" onClick={guardar}>Guardar</button></div>
        </div>
      )}
      <div className="tarjeta overflow-hidden">
        <table className="tabla">
          <thead><tr><th className="w-32">Código</th><th>Nombre</th><th>Tipo</th><th>Naturaleza</th><th>Uso</th></tr></thead>
          <tbody>{datos.map((c) => (
            <tr key={c.id} className={c.nivel === 1 ? 'bg-tinta-50' : ''}>
              <td className="font-mono text-tinta-400">{c.codigo}</td>
              <td style={{ paddingLeft: `${(c.nivel - 1) * 20 + 12}px` }} className={c.acepta_movimientos ? '' : 'font-semibold'}>{c.nombre}</td>
              <td><span className={`pastilla ${colores[c.tipo]}`}>{c.tipo}</span></td>
              <td className="text-tinta-600">{c.naturaleza}</td>
              <td className="text-xs text-tinta-400">{c.acepta_movimientos ? 'detalle' : 'de mayor'}</td>
            </tr>))}
          </tbody>
        </table>
      </div>
    </>
  )
}
