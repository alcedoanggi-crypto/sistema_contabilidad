import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, dinero, fecha, hoy } from '../api'
import { Aviso, Cargando, Estado, Titulo, useApi } from '../componentes/ui'

export default function FacturaDetalle() {
  const { id } = useParams()
  const { datos: f, error, cargando, recargar } = useApi(`/facturas/${id}`)
  const bancos = useApi('/bancos')
  const [pago, setPago] = useState(null)
  const [cancelar, setCancelar] = useState(null)
  const [msg, setMsg] = useState({ tipo: 'error', texto: '' })

  const enviar = async (fn, ok) => {
    setMsg({ tipo: 'error', texto: '' })
    try { await fn(); setMsg({ tipo: 'ok', texto: ok }); setPago(null); setCancelar(null); recargar() }
    catch (e) { setMsg({ tipo: 'error', texto: e.message }) }
  }
  if (cargando) return <Cargando />
  if (error) return <Aviso>{error}</Aviso>
  const venta = f.tipo === 'ingreso'

  return (
    <>
      <Titulo titulo={`Factura ${f.folio}`} subtitulo={`${venta ? 'Venta a' : 'Compra a'} ${f.tercero}`}>
        {f.estado === 'vigente' && <button className="btn-verde" onClick={() => setPago({ fecha: hoy(), monto: f.saldo, cuenta_bancaria_id: bancos.datos?.[0]?.id, referencia: '' })}>
          Registrar {venta ? 'cobro' : 'pago'}</button>}
        {f.estado === 'vigente' && !f.pagos.length && <button className="btn-peligro" onClick={() => setCancelar({ fecha: hoy(), motivo: '' })}>Cancelar factura</button>}
        <button className="btn-borde" onClick={() => window.print()}>Imprimir</button>
      </Titulo>
      <Aviso tipo={msg.tipo}>{msg.texto}</Aviso>

      {pago && (
        <div className="tarjeta no-imprimir mb-4 grid gap-3 p-4 md:grid-cols-5">
          <div><label className="etiqueta">Fecha</label><input type="date" className="campo" value={pago.fecha} onChange={(e) => setPago({ ...pago, fecha: e.target.value })} /></div>
          <div><label className="etiqueta">Monto ({f.moneda})</label><input className="campo num" value={pago.monto} onChange={(e) => setPago({ ...pago, monto: e.target.value })} /></div>
          <div><label className="etiqueta">Banco</label>
            <select className="campo" value={pago.cuenta_bancaria_id} onChange={(e) => setPago({ ...pago, cuenta_bancaria_id: Number(e.target.value) })}>
              {(bancos.datos || []).map((b) => <option key={b.id} value={b.id}>{b.banco} {b.numero}</option>)}
            </select></div>
          <div><label className="etiqueta">Referencia</label><input className="campo" value={pago.referencia} onChange={(e) => setPago({ ...pago, referencia: e.target.value })} placeholder="TRF-…" /></div>
          <div className="flex items-end gap-2">
            <button className="btn-borde" onClick={() => setPago(null)}>Cerrar</button>
            <button className="btn-verde" onClick={() => enviar(() => api(`/facturas/${f.id}/pagos`, { metodo: 'POST', datos: pago }), 'Pago registrado y contabilizado')}>Guardar</button>
          </div>
        </div>
      )}
      {cancelar && (
        <div className="tarjeta no-imprimir mb-4 grid gap-3 p-4 md:grid-cols-[160px_1fr_auto]">
          <div><label className="etiqueta">Fecha</label><input type="date" className="campo" value={cancelar.fecha} onChange={(e) => setCancelar({ ...cancelar, fecha: e.target.value })} /></div>
          <div><label className="etiqueta">Motivo</label><input className="campo" value={cancelar.motivo} onChange={(e) => setCancelar({ ...cancelar, motivo: e.target.value })} /></div>
          <div className="flex items-end gap-2">
            <button className="btn-borde" onClick={() => setCancelar(null)}>Cerrar</button>
            <button className="btn-peligro" disabled={cancelar.motivo.length < 3}
              onClick={() => enviar(() => api(`/facturas/${f.id}/cancelar`, { metodo: 'POST', datos: cancelar }), 'Factura cancelada: su póliza se revirtió')}>Cancelar factura</button>
          </div>
        </div>
      )}

      <div className="tarjeta mb-4 grid gap-4 p-5 text-sm sm:grid-cols-3 lg:grid-cols-6">
        <div><div className="etiqueta">Estado</div><Estado valor={f.estado} /></div>
        <div><div className="etiqueta">Fecha</div>{fecha(f.fecha)}</div>
        <div><div className="etiqueta">Vence</div>{fecha(f.vencimiento)}</div>
        <div><div className="etiqueta">Moneda</div>{f.moneda}{f.moneda !== 'USD' && ` · TC ${Number(f.tipo_cambio)}`}</div>
        <div><div className="etiqueta">Saldo</div><span className="font-mono font-semibold">{dinero(f.saldo)}</span></div>
        <div><div className="etiqueta">Póliza</div><Link to={`/polizas/${f.poliza_id}`} className="font-mono text-tinta-700 hover:underline">{f.folio_poliza}</Link></div>
      </div>

      <div className="tarjeta mb-4 overflow-hidden">
        <table className="tabla">
          <thead><tr><th>Descripción</th><th>Cuenta</th><th className="text-right">Cantidad</th><th className="text-right">Precio</th><th className="text-right">Importe</th></tr></thead>
          <tbody>
            {f.lineas.map((l) => (
              <tr key={l.id}><td>{l.descripcion}</td><td><span className="font-mono text-tinta-400">{l.cuenta_codigo}</span> {l.cuenta_nombre}</td>
                <td className="num">{Number(l.cantidad)}</td><td className="num">{dinero(l.precio_unitario)}</td><td className="num">{dinero(l.importe)}</td></tr>
            ))}
          </tbody>
          <tfoot className="text-sm">
            <tr><td colSpan={4} className="px-3 py-1 text-right">Subtotal</td><td className="num px-3">{dinero(f.subtotal)}</td></tr>
            {f.impuestos.map((i) => (
              <tr key={i.id}><td colSpan={4} className="px-3 py-1 text-right text-tinta-600">{i.tipo === 'retencion' ? '−' : '+'} {i.nombre}</td><td className="num px-3">{dinero(i.importe)}</td></tr>
            ))}
            <tr className="bg-tinta-50 font-bold"><td colSpan={4} className="px-3 py-2 text-right">Total {f.moneda}</td><td className="num px-3">{dinero(f.total)}</td></tr>
          </tfoot>
        </table>
      </div>

      {f.pagos.length > 0 && (
        <div className="tarjeta overflow-hidden">
          <div className="px-5 py-3 font-semibold text-tinta-900">{venta ? 'Cobros' : 'Pagos'}</div>
          <table className="tabla">
            <thead><tr><th>Fecha</th><th>Banco</th><th>Referencia</th><th>Póliza</th><th className="text-right">TC</th><th className="text-right">Monto</th></tr></thead>
            <tbody>
              {f.pagos.map((p) => (
                <tr key={p.id}><td>{fecha(p.fecha)}</td><td>{p.banco}</td><td className="font-mono">{p.referencia}</td>
                  <td><Link to={`/polizas/${p.poliza_id}`} className="font-mono text-tinta-700 hover:underline">{p.folio_poliza}</Link></td>
                  <td className="num">{Number(p.tipo_cambio)}</td><td className="num">{dinero(p.monto)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
