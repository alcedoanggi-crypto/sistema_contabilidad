import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, dinero, fecha, hoy } from '../api'
import { Aviso, Cargando, Estado, Titulo, useApi } from '../componentes/ui'

export default function PolizaDetalle() {
  const { id } = useParams()
  const navegar = useNavigate()
  const { datos: p, error, cargando, recargar } = useApi(`/polizas/${id}`)
  const [reversa, setReversa] = useState(null)
  const [msg, setMsg] = useState('')

  const accion = async (fn) => {
    setMsg('')
    try { await fn() } catch (e) { setMsg(e.message) }
  }
  if (cargando) return <Cargando />
  if (error) return <Aviso>{error}</Aviso>
  const extranjera = p.moneda !== 'USD'

  return (
    <>
      <Titulo titulo={p.folio ? `Póliza ${p.folio}` : 'Póliza en borrador'} subtitulo={p.concepto}>
        {p.estado === 'borrador' && <>
          <Link to={`/polizas/${p.id}/editar`} className="btn-borde">Editar</Link>
          <button className="btn-peligro" onClick={() => accion(async () => { await api(`/polizas/${p.id}`, { metodo: 'DELETE' }); navegar('/polizas') })}>Eliminar</button>
          <button className="btn-verde" onClick={() => accion(async () => { await api(`/polizas/${p.id}/contabilizar`, { metodo: 'POST' }); recargar() })}>Contabilizar</button>
        </>}
        {p.estado === 'contabilizada' && p.origen !== 'reversa' &&
          <button className="btn-peligro" onClick={() => setReversa({ fecha: hoy() > p.fecha ? hoy() : p.fecha, motivo: '' })}>Cancelar con reversa</button>}
        <button className="btn-borde" onClick={() => window.print()}>Imprimir</button>
      </Titulo>
      <Aviso>{msg}</Aviso>
      {p.estado === 'contabilizada' && <Aviso tipo="info">Las pólizas contabilizadas no se editan ni se borran. Para corregirla se cancela con una póliza de reversa (cargos y abonos invertidos).</Aviso>}
      {p.periodo_cerrado && <Aviso tipo="info">El periodo de esta póliza está cerrado. Para corregirla, genera la reversa con fecha de un mes abierto.</Aviso>}

      {reversa && (
        <div className="tarjeta no-imprimir mb-4 grid gap-3 border-red-200 p-4 md:grid-cols-[160px_1fr_auto]">
          <div><label className="etiqueta">Fecha de la reversa</label>
            <input type="date" className="campo" value={reversa.fecha} onChange={(e) => setReversa({ ...reversa, fecha: e.target.value })} /></div>
          <div><label className="etiqueta">Motivo</label>
            <input className="campo" autoFocus value={reversa.motivo} onChange={(e) => setReversa({ ...reversa, motivo: e.target.value })} placeholder="Ej. cuenta de gasto equivocada" /></div>
          <div className="flex items-end gap-2">
            <button className="btn-borde" onClick={() => setReversa(null)}>Cerrar</button>
            <button className="btn-peligro" disabled={reversa.motivo.length < 3}
              onClick={() => accion(async () => { const r = await api(`/polizas/${p.id}/revertir`, { metodo: 'POST', datos: reversa }); setReversa(null); navegar(`/polizas/${r.id}`) })}>
              Generar reversa</button>
          </div>
        </div>
      )}

      <div className="tarjeta mb-4 grid gap-4 p-5 text-sm sm:grid-cols-3 lg:grid-cols-6">
        <div><div className="etiqueta">Estado</div><Estado valor={p.estado} /></div>
        <div><div className="etiqueta">Fecha</div>{fecha(p.fecha)}</div>
        <div><div className="etiqueta">Tipo</div><span className="capitalize">{p.tipo}</span></div>
        <div><div className="etiqueta">Origen</div>{p.origen}</div>
        <div><div className="etiqueta">Moneda</div>{p.moneda}{extranjera && ` · TC ${Number(p.tipo_cambio)}`}</div>
        <div><div className="etiqueta">Capturó</div>{p.creado_por}</div>
        {p.folio_reversa_de && <div className="sm:col-span-3"><div className="etiqueta">Revierte a</div><Link className="font-mono text-tinta-700 hover:underline" to={`/polizas/${p.reversa_de}`}>{p.folio_reversa_de}</Link></div>}
        {p.folio_cancelada_por && <div className="sm:col-span-3"><div className="etiqueta">Cancelada por</div>
          <Link className="font-mono text-tinta-700 hover:underline" to={`/polizas/${p.cancelada_por}`}>{p.folio_cancelada_por}</Link> · {p.motivo_cancelacion}</div>}
      </div>

      <div className="tarjeta overflow-hidden">
        <table className="tabla">
          <thead><tr><th>Cuenta</th><th>Descripción</th><th className="text-right">Debe</th><th className="text-right">Haber</th>
            {extranjera && <><th className="text-right">Debe USD</th><th className="text-right">Haber USD</th></>}</tr></thead>
          <tbody>
            {p.lineas.map((l) => (
              <tr key={l.id}>
                <td><span className="font-mono text-tinta-400">{l.cuenta_codigo}</span> {l.cuenta_nombre}</td>
                <td className="text-tinta-600">{l.descripcion}</td>
                <td className="num">{Number(l.debe) ? dinero(l.debe) : ''}</td>
                <td className="num">{Number(l.haber) ? dinero(l.haber) : ''}</td>
                {extranjera && <><td className="num text-tinta-400">{Number(l.debe_base) ? dinero(l.debe_base) : ''}</td>
                  <td className="num text-tinta-400">{Number(l.haber_base) ? dinero(l.haber_base) : ''}</td></>}
              </tr>
            ))}
          </tbody>
          <tfoot><tr className="bg-tinta-50 font-semibold"><td colSpan={2} className="px-3 py-2">Totales</td>
            <td className="num px-3">{dinero(p.total_debe)}</td><td className="num px-3">{dinero(p.total_haber)}</td>{extranjera && <td colSpan={2} />}</tr></tfoot>
        </table>
      </div>
    </>
  )
}
