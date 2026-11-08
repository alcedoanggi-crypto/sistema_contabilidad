import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, dinero, hoy } from '../api'
import { Aviso, SelectorCuenta, Titulo, useApi } from '../componentes/ui'

const lineaVacia = () => ({ clave: crypto.randomUUID(), descripcion: '', cuenta: null, cantidad: '1', precio_unitario: '' })

export default function FacturaForm() {
  const [params] = useSearchParams()
  const tipo = params.get('tipo') === 'gasto' ? 'gasto' : 'ingreso'
  const navegar = useNavigate()
  const terceros = useApi(`/terceros?tipo=${tipo === 'ingreso' ? 'cliente' : 'proveedor'}`)
  const impuestos = useApi('/impuestos')
  const monedas = useApi('/monedas')
  const [f, setF] = useState({ folio: '', tercero_id: '', fecha: hoy(), vencimiento: '', moneda: 'USD', notas: '' })
  const [lineas, setLineas] = useState([lineaVacia()])
  const [imps, setImps] = useState(['IVA16'])
  const [totales, setTotales] = useState(null)
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)

  const lineasValidas = lineas.filter((l) => l.cuenta && Number(l.cantidad) > 0 && l.precio_unitario !== '')
  const cuerpo = () => ({
    ...f, tipo, tercero_id: Number(f.tercero_id), vencimiento: f.vencimiento || null, impuestos: imps,
    lineas: lineasValidas.map((l) => ({ descripcion: l.descripcion || 'Concepto', cuenta_id: l.cuenta.id, cantidad: l.cantidad, precio_unitario: l.precio_unitario })),
  })

  // Totales calculados por el mismo código del servidor (vista previa, no guarda nada)
  useEffect(() => {
    if (!lineasValidas.length) return setTotales(null)
    const t = setTimeout(() => api('/facturas/calcular', { metodo: 'POST', datos: { ...cuerpo(), folio: 'x', tercero_id: 1 } })
      .then(setTotales).catch(() => setTotales(null)), 250)
    return () => clearTimeout(t)
  }, [JSON.stringify(lineas), imps.join()])

  const cambiar = (i, campo, valor) => setLineas((ls) => ls.map((l, k) => (k === i ? { ...l, [campo]: valor } : l)))
  const guardar = async () => {
    setError('')
    if (!f.tercero_id) return setError(`Elige el ${tipo === 'ingreso' ? 'cliente' : 'proveedor'}`)
    if (!lineasValidas.length) return setError('Agrega al menos una línea con cuenta, cantidad y precio')
    setGuardando(true)
    try { const r = await api('/facturas', { metodo: 'POST', datos: cuerpo() }); navegar(`/facturas/${r.id}`) }
    catch (e) { setError(e.message); setGuardando(false) }
  }

  const disponibles = (impuestos.datos || []).filter((i) => i.activo)
  return (
    <>
      <Titulo titulo={tipo === 'ingreso' ? 'Nueva factura de venta' : 'Nueva factura de compra'}
        subtitulo="Al guardarla se genera y contabiliza su póliza con IVA y retenciones" />
      <Aviso>{error}</Aviso>
      <div className="tarjeta mb-4 grid gap-4 p-5 md:grid-cols-6">
        <div><label className="etiqueta">Folio</label><input className="campo" autoFocus value={f.folio} onChange={(e) => setF({ ...f, folio: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="etiqueta">{tipo === 'ingreso' ? 'Cliente' : 'Proveedor'}</label>
          <select className="campo" value={f.tercero_id} onChange={(e) => setF({ ...f, tercero_id: e.target.value })}>
            <option value="">Elegir…</option>
            {(terceros.datos || []).map((t) => <option key={t.id} value={t.id}>{t.nombre} ({t.dias_credito} días)</option>)}
          </select></div>
        <div><label className="etiqueta">Fecha</label><input type="date" className="campo" value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} /></div>
        <div><label className="etiqueta">Vence</label><input type="date" className="campo" value={f.vencimiento} onChange={(e) => setF({ ...f, vencimiento: e.target.value })} title="Si lo dejas vacío se usan los días de crédito" /></div>
        <div><label className="etiqueta">Moneda</label>
          <select className="campo" value={f.moneda} onChange={(e) => setF({ ...f, moneda: e.target.value })}>
            {(monedas.datos || []).map((m) => <option key={m.codigo}>{m.codigo}</option>)}
          </select></div>
      </div>

      <div className="tarjeta overflow-visible">
        <table className="tabla">
          <thead><tr><th>Descripción</th><th className="w-72">Cuenta de {tipo === 'ingreso' ? 'ingreso' : 'gasto'}</th><th className="w-24 text-right">Cantidad</th><th className="w-32 text-right">Precio</th><th className="w-32 text-right">Importe</th><th className="w-10" /></tr></thead>
          <tbody>
            {lineas.map((l, i) => (
              <tr key={l.clave}>
                <td><input className="campo" value={l.descripcion} onChange={(e) => cambiar(i, 'descripcion', e.target.value)} placeholder="Concepto" /></td>
                <td><SelectorCuenta valor={l.cuenta} tipo={tipo === 'ingreso' ? 'ingreso' : undefined} onCambio={(c) => cambiar(i, 'cuenta', c)} /></td>
                <td><input className="campo num" value={l.cantidad} onChange={(e) => cambiar(i, 'cantidad', e.target.value.replace(/[^\d.]/g, ''))} /></td>
                <td><input className="campo num" value={l.precio_unitario} onChange={(e) => cambiar(i, 'precio_unitario', e.target.value.replace(/[^\d.]/g, ''))} /></td>
                <td className="num">{totales?.importes?.[lineasValidas.indexOf(l)] !== undefined && lineasValidas.includes(l) ? dinero(totales.importes[lineasValidas.indexOf(l)]) : ''}</td>
                <td><button disabled={lineas.length === 1} onClick={() => setLineas((ls) => ls.filter((_, k) => k !== i))} className="text-tinta-400 hover:text-red-600 disabled:opacity-30">✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-3 py-2"><button onClick={() => setLineas((ls) => [...ls, lineaVacia()])} className="text-sm text-tinta-600 hover:underline">+ Agregar línea</button></div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="tarjeta p-5">
          <div className="etiqueta">Impuestos</div>
          <div className="space-y-1.5">
            {disponibles.map((i) => (
              <label key={i.codigo} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={imps.includes(i.codigo)}
                  onChange={(e) => setImps((a) => (e.target.checked ? [...a, i.codigo] : a.filter((x) => x !== i.codigo)))} />
                {i.nombre} <span className="text-xs text-tinta-400">({i.tipo === 'traslado' ? 'se suma' : 'se resta'})</span>
              </label>
            ))}
          </div>
          <label className="etiqueta mt-4">Notas</label>
          <input className="campo" value={f.notas} onChange={(e) => setF({ ...f, notas: e.target.value })} />
        </div>
        <div className="tarjeta p-5">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt>Subtotal</dt><dd className="font-mono">{dinero(totales?.subtotal ?? 0)}</dd></div>
            {(totales?.impuestos || []).map((i) => (
              <div key={i.codigo} className="flex justify-between text-tinta-600"><dt>{i.tipo === 'retencion' ? '−' : '+'} {i.nombre}</dt><dd className="font-mono">{dinero(i.importe)}</dd></div>
            ))}
            <div className="flex justify-between border-t border-tinta-100 pt-2 text-lg font-bold"><dt>Total</dt><dd className="font-mono">{dinero(totales?.total ?? 0)} {f.moneda}</dd></div>
          </dl>
          <div className="mt-5 flex justify-end gap-2">
            <button className="btn-borde" onClick={() => navegar(-1)}>Cancelar</button>
            <button className="btn-verde" disabled={guardando} onClick={guardar}>Guardar y contabilizar</button>
          </div>
        </div>
      </div>
    </>
  )
}
