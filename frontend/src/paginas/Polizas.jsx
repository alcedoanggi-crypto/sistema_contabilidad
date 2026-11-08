import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { dinero, fecha } from '../api'
import { Aviso, Cargando, Estado, Titulo, useApi } from '../componentes/ui'

export default function Polizas() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') || '')
  const estado = params.get('estado') || ''
  const consulta = new URLSearchParams({ ...(estado && { estado }), ...(params.get('q') && { q: params.get('q') }) })
  const { datos, error, cargando } = useApi(`/polizas?${consulta}`)

  const filtrar = (cambios) => {
    const n = new URLSearchParams(params)
    Object.entries(cambios).forEach(([k, v]) => (v ? n.set(k, v) : n.delete(k)))
    setParams(n)
  }

  return (
    <>
      <Titulo titulo="Pólizas" subtitulo="Asientos contables con partida doble">
        <Link to="/polizas/nueva" className="btn-primario">+ Nueva póliza</Link>
      </Titulo>
      <div className="mb-4 flex flex-wrap gap-2">
        <form onSubmit={(e) => { e.preventDefault(); filtrar({ q }) }} className="flex gap-2">
          <input className="campo w-64" placeholder="Buscar concepto o folio…" value={q} onChange={(e) => setQ(e.target.value)} />
          <button className="btn-borde">Buscar</button>
        </form>
        {['', 'borrador', 'contabilizada', 'cancelada'].map((e) => (
          <button key={e} onClick={() => filtrar({ estado: e })}
            className={`btn ${estado === e ? 'bg-tinta-700 text-white' : 'border border-tinta-200 bg-white text-tinta-600'}`}>
            {e || 'Todas'}
          </button>
        ))}
      </div>
      <Aviso>{error}</Aviso>
      {cargando ? <Cargando /> : (
        <div className="tarjeta overflow-hidden">
          <table className="tabla">
            <thead><tr><th>Folio</th><th>Fecha</th><th>Tipo</th><th>Concepto</th><th>Origen</th><th>Estado</th><th className="text-right">Importe</th></tr></thead>
            <tbody>
              {datos.map((p) => (
                <tr key={p.id} className="hover:bg-tinta-50">
                  <td className="font-mono"><Link to={`/polizas/${p.id}`} className="text-tinta-700 hover:underline">{p.folio || 'borrador'}</Link></td>
                  <td className="whitespace-nowrap">{fecha(p.fecha)}</td>
                  <td className="capitalize">{p.tipo}</td>
                  <td>{p.concepto}</td>
                  <td className="text-tinta-400">{p.origen}</td>
                  <td><Estado valor={p.estado} /></td>
                  <td className="num whitespace-nowrap">{dinero(p.total)} <span className="text-xs text-tinta-400">{p.moneda}</span></td>
                </tr>
              ))}
              {!datos.length && <tr><td colSpan={7} className="py-10 text-center text-tinta-400">No hay pólizas con ese filtro</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
