import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { descargar, dinero, fecha } from '../api'
import { Aviso, Cargando, Titulo, useApi } from '../componentes/ui'

const REPORTES = [
  ['balanza', 'Balanza de comprobación'], ['balance', 'Balance general'], ['resultados', 'Estado de resultados'],
  ['diario', 'Libro diario'], ['mayor', 'Libro mayor'], ['antiguedad', 'Antigüedad de saldos'],
]
const ruta = (r, p) => ({
  balanza: `/reportes/balanza?desde=${p.desde}&hasta=${p.hasta}`,
  balance: `/reportes/balance-general?corte=${p.hasta}`,
  resultados: `/reportes/estado-resultados?desde=${p.desde}&hasta=${p.hasta}`,
  diario: `/reportes/libro-diario?desde=${p.desde}&hasta=${p.hasta}`,
  mayor: p.cuenta ? `/reportes/libro-mayor?cuenta_id=${p.cuenta}&desde=${p.desde}&hasta=${p.hasta}` : null,
  antiguedad: `/reportes/antiguedad?tipo=${p.tipo}&corte=${p.hasta}`,
}[r])

const Monto = ({ v, fuerte }) => <td className={`num ${fuerte ? 'font-semibold' : ''} ${Number(v) < 0 ? 'text-red-700' : ''}`}>{v === null || v === undefined ? '' : dinero(v)}</td>
const Sangria = ({ c }) => <td style={{ paddingLeft: `${(c.nivel - 1) * 18 + 12}px` }} className={c.acepta_movimientos ? '' : 'font-semibold'}>{c.nombre}</td>

export default function Reportes() {
  const [qs, setQs] = useSearchParams()
  const [p, setP] = useState({ desde: '2026-01-01', hasta: '2026-11-08', cuenta: '', tipo: 'cxc' })
  const r = qs.get('r') || 'balanza'
  const cuentas = useApi('/cuentas')
  const { datos: d, error, cargando } = useApi(ruta(r, p))
  const [msg, setMsg] = useState('')

  const exportar = (formato) => descargar(`${ruta(r, p)}&formato=${formato}`, `${r}.${formato}`).catch((e) => setMsg(e.message))
  const titulo = REPORTES.find(([k]) => k === r)[1]

  return (
    <>
      <Titulo titulo="Reportes" subtitulo="Calculados por funciones de PostgreSQL · cifras en USD">
        <button className="btn-borde" onClick={() => window.print()}>Imprimir</button>
        <button className="btn-borde" onClick={() => exportar('pdf')}>PDF</button>
        <button className="btn-borde" onClick={() => exportar('xlsx')}>Excel</button>
      </Titulo>
      <div className="no-imprimir mb-4 flex flex-wrap gap-1.5">
        {REPORTES.map(([k, t]) => (
          <button key={k} onClick={() => setQs({ r: k })} className={`btn ${r === k ? 'bg-tinta-700 text-white' : 'border border-tinta-200 bg-white text-tinta-600'}`}>{t}</button>
        ))}
      </div>
      <div className="tarjeta no-imprimir mb-4 flex flex-wrap items-end gap-4 p-4">
        {!['balance', 'antiguedad'].includes(r) && <div><label className="etiqueta">Desde</label><input type="date" className="campo" value={p.desde} onChange={(e) => setP({ ...p, desde: e.target.value })} /></div>}
        <div><label className="etiqueta">{['balance', 'antiguedad'].includes(r) ? 'Fecha de corte' : 'Hasta'}</label>
          <input type="date" className="campo" value={p.hasta} onChange={(e) => setP({ ...p, hasta: e.target.value })} /></div>
        {r === 'mayor' && <div className="min-w-72"><label className="etiqueta">Cuenta</label>
          <select className="campo" value={p.cuenta} onChange={(e) => setP({ ...p, cuenta: e.target.value })}>
            <option value="">Elegir cuenta…</option>
            {(cuentas.datos || []).map((c) => <option key={c.id} value={c.id}>{c.codigo} {'· '.repeat(c.nivel - 1)}{c.nombre}</option>)}
          </select></div>}
        {r === 'antiguedad' && <div><label className="etiqueta">Tipo</label>
          <select className="campo" value={p.tipo} onChange={(e) => setP({ ...p, tipo: e.target.value })}>
            <option value="cxc">Cuentas por cobrar</option><option value="cxp">Cuentas por pagar</option></select></div>}
      </div>
      <Aviso>{error || msg}</Aviso>

      <div className="tarjeta overflow-hidden">
        <div className="border-b border-tinta-100 px-5 py-4">
          <div className="text-xs font-semibold uppercase tracking-wide text-tinta-400">Nexo Soluciones Digitales S.A.</div>
          <h2 className="text-lg font-bold text-tinta-900">{titulo}</h2>
          <div className="text-sm text-tinta-400">{['balance', 'antiguedad'].includes(r) ? `Al ${fecha(p.hasta)}` : `Del ${fecha(p.desde)} al ${fecha(p.hasta)}`}</div>
        </div>
        {r === 'mayor' && !p.cuenta ? <Cargando>Elige una cuenta para ver su libro mayor</Cargando>
          : cargando || !d ? <Cargando /> : <Contenido r={r} d={d} />}
      </div>
    </>
  )
}

function Contenido({ r, d }) {
  if (r === 'balanza') return (
    <table className="tabla">
      <thead><tr><th>Código</th><th>Cuenta</th><th className="text-right">Saldo inicial</th><th className="text-right">Debe</th><th className="text-right">Haber</th><th className="text-right">Deudor</th><th className="text-right">Acreedor</th></tr></thead>
      <tbody>{d.cuentas.map((c) => (
        <tr key={c.cuenta_id}><td className="font-mono text-tinta-400">{c.codigo}</td><Sangria c={c} />
          <Monto v={c.saldo_inicial} /><Monto v={c.debe} /><Monto v={c.haber} /><Monto v={Number(c.saldo_deudor) || null} /><Monto v={Number(c.saldo_acreedor) || null} /></tr>))}
      </tbody>
      <tfoot><tr className="bg-tinta-50 font-bold"><td colSpan={3} className="px-3 py-2">Totales {d.cuadra ? '✓ cuadra' : '✗ no cuadra'}</td>
        <Monto v={d.totales.debe} /><Monto v={d.totales.haber} /><Monto v={d.totales.saldo_deudor} /><Monto v={d.totales.saldo_acreedor} /></tr></tfoot>
    </table>
  )
  if (r === 'balance') return (
    <div className="grid gap-px bg-tinta-100 md:grid-cols-2">
      {[['activo', 'Activo'], ['pasivo_capital', 'Pasivo y capital']].map(([lado, nombre]) => (
        <div key={lado} className="bg-white">
          <table className="tabla">
            <thead><tr><th>{nombre}</th><th className="text-right">Importe</th></tr></thead>
            <tbody>
              {(lado === 'activo' ? ['activo'] : ['pasivo', 'capital']).flatMap((s) => [
                ...d[s].cuentas.map((c, i) => <tr key={s + i}><Sangria c={{ ...c, nivel: c.nivel || 2 }} /><Monto v={c.importe} fuerte={!c.acepta_movimientos} /></tr>),
                <tr key={s + 't'} className="bg-tinta-50"><td className="font-semibold capitalize">Total {s}</td><Monto v={d[s].total} fuerte /></tr>,
              ])}
            </tbody>
            <tfoot><tr className="bg-tinta-100 font-bold"><td className="px-3 py-2">{lado === 'activo' ? 'TOTAL ACTIVO' : 'TOTAL PASIVO + CAPITAL'}</td>
              <Monto v={lado === 'activo' ? d.activo.total : d.total_pasivo_capital} fuerte /></tr></tfoot>
          </table>
        </div>
      ))}
      <div className={`col-span-full px-5 py-2 text-sm font-semibold ${d.cuadra ? 'bg-menta-50 text-menta-700' : 'bg-red-50 text-red-700'}`}>
        {d.cuadra ? '✓ Activo = Pasivo + Capital' : '✗ El balance no cuadra'}</div>
    </div>
  )
  if (r === 'resultados') return (
    <table className="tabla">
      <tbody>
        {[['Ingresos', d.ingresos, d.total_ingresos], ['Gastos', d.gastos, d.total_gastos]].flatMap(([t, filas, total]) => [
          <tr key={t} className="bg-tinta-50"><td colSpan={2} className="font-bold uppercase">{t}</td></tr>,
          ...filas.map((c) => <tr key={c.cuenta_id}><Sangria c={c} /><Monto v={c.importe} fuerte={!c.acepta_movimientos} /></tr>),
          <tr key={t + 't'}><td className="font-semibold">Total {t.toLowerCase()}</td><Monto v={total} fuerte /></tr>,
        ])}
      </tbody>
      <tfoot><tr className={`font-bold ${Number(d.utilidad) >= 0 ? 'bg-menta-50 text-menta-700' : 'bg-red-50 text-red-700'}`}>
        <td className="px-3 py-3 text-base">{Number(d.utilidad) >= 0 ? 'UTILIDAD' : 'PÉRDIDA'} DEL PERIODO</td><Monto v={d.utilidad} fuerte /></tr></tfoot>
    </table>
  )
  if (r === 'diario') return (
    <table className="tabla">
      <thead><tr><th>Fecha</th><th>Cuenta</th><th>Concepto</th><th className="text-right">Debe</th><th className="text-right">Haber</th></tr></thead>
      <tbody>{d.polizas.flatMap((p) => [
        <tr key={p.poliza_id} className="bg-tinta-50"><td className="whitespace-nowrap">{fecha(p.fecha)}</td>
          <td className="font-mono"><Link to={`/polizas/${p.poliza_id}`} className="text-tinta-700 hover:underline">{p.folio}</Link></td>
          <td colSpan={3} className="font-medium">{p.concepto}{p.estado_poliza === 'cancelada' && <span className="ml-2 text-xs text-red-600">(cancelada)</span>}</td></tr>,
        ...p.lineas.map((l) => <tr key={l.linea_id}><td /><td className="pl-6"><span className="font-mono text-tinta-400">{l.cuenta_codigo}</span> {l.cuenta_nombre}</td>
          <td className="text-tinta-400">{l.descripcion}</td><Monto v={Number(l.debe_base) || null} /><Monto v={Number(l.haber_base) || null} /></tr>),
      ])}</tbody>
      <tfoot><tr className="bg-tinta-100 font-bold"><td colSpan={3} className="px-3 py-2">Totales</td><Monto v={d.total_debe} /><Monto v={d.total_haber} /></tr></tfoot>
    </table>
  )
  if (r === 'mayor') return (
    <table className="tabla">
      <thead><tr><th>Fecha</th><th>Póliza</th><th>Concepto</th><th className="text-right">Debe</th><th className="text-right">Haber</th><th className="text-right">Saldo</th></tr></thead>
      <tbody>
        <tr className="bg-tinta-50"><td colSpan={5} className="font-semibold">{d.cuenta.codigo} {d.cuenta.nombre} · saldo inicial</td><Monto v={d.saldo_inicial} fuerte /></tr>
        {d.movimientos.map((m, i) => (
          <tr key={i}><td className="whitespace-nowrap">{fecha(m.fecha)}</td>
            <td className="font-mono"><Link to={`/polizas/${m.poliza_id}`} className="text-tinta-700 hover:underline">{m.folio}</Link></td>
            <td>{m.concepto}</td><Monto v={Number(m.debe) || null} /><Monto v={Number(m.haber) || null} /><Monto v={m.saldo} /></tr>))}
      </tbody>
      <tfoot><tr className="bg-tinta-100 font-bold"><td colSpan={3} className="px-3 py-2">Totales y saldo final</td><Monto v={d.total_debe} /><Monto v={d.total_haber} /><Monto v={d.saldo_final} /></tr></tfoot>
    </table>
  )
  const cols = [['por_vencer', 'Por vencer'], ['d0_30', '1-30 días'], ['d31_60', '31-60'], ['d61_90', '61-90'], ['mas_90', 'Más de 90'], ['total', 'Total']]
  return (
    <>
      <table className="tabla">
        <thead><tr><th>{d.tipo === 'cxc' ? 'Cliente' : 'Proveedor'}</th>{cols.map(([k, t]) => <th key={k} className="text-right">{t}</th>)}</tr></thead>
        <tbody>{d.terceros.map((t) => <tr key={t.tercero_id}><td>{t.tercero}</td>{cols.map(([k]) => <Monto key={k} v={Number(t[k]) || null} fuerte={k === 'total'} />)}</tr>)}</tbody>
        <tfoot><tr className="bg-tinta-100 font-bold"><td className="px-3 py-2">Totales</td>{cols.map(([k]) => <Monto key={k} v={d.totales[k]} />)}</tr></tfoot>
      </table>
      <div className="border-t border-tinta-100 px-5 py-3 text-sm font-semibold text-tinta-900">Detalle por factura</div>
      <table className="tabla">
        <thead><tr><th>Folio</th><th>{d.tipo === 'cxc' ? 'Cliente' : 'Proveedor'}</th><th>Vence</th><th className="text-right">Días vencida</th><th className="text-right">Saldo USD</th></tr></thead>
        <tbody>{d.facturas.map((f) => (
          <tr key={f.factura_id}><td className="font-mono"><Link to={`/facturas/${f.factura_id}`} className="text-tinta-700 hover:underline">{f.folio}</Link></td>
            <td>{f.tercero}</td><td>{fecha(f.vencimiento)}</td>
            <td className={`num ${f.dias_vencido > 60 ? 'font-semibold text-red-700' : ''}`}>{f.dias_vencido > 0 ? f.dias_vencido : 'al día'}</td><Monto v={f.saldo_base} /></tr>))}</tbody>
      </table>
    </>
  )
}
