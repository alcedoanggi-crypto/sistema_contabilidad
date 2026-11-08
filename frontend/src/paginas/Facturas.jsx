import { Link, useSearchParams } from 'react-router-dom'
import { dinero, fecha } from '../api'
import { Aviso, Cargando, Estado, Titulo, useApi } from '../componentes/ui'

export default function Facturas() {
  const [params, setParams] = useSearchParams()
  const tipo = params.get('tipo') || ''
  const { datos, error, cargando } = useApi(`/facturas${tipo ? `?tipo=${tipo}` : ''}`)

  return (
    <>
      <Titulo titulo="Facturas" subtitulo="Cada factura genera su asiento contable automáticamente">
        <Link to="/facturas/nueva?tipo=ingreso" className="btn-primario">+ Factura de venta</Link>
        <Link to="/facturas/nueva?tipo=gasto" className="btn-borde">+ Factura de compra</Link>
      </Titulo>
      <div className="mb-4 flex gap-2">
        {[['', 'Todas'], ['ingreso', 'Ventas (por cobrar)'], ['gasto', 'Compras (por pagar)']].map(([v, t]) => (
          <button key={v} onClick={() => setParams(v ? { tipo: v } : {})}
            className={`btn ${tipo === v ? 'bg-tinta-700 text-white' : 'border border-tinta-200 bg-white text-tinta-600'}`}>{t}</button>
        ))}
      </div>
      <Aviso>{error}</Aviso>
      {cargando ? <Cargando /> : (
        <div className="tarjeta overflow-hidden">
          <table className="tabla">
            <thead><tr><th>Folio</th><th>Tipo</th><th>Cliente / proveedor</th><th>Fecha</th><th>Vence</th><th>Estado</th><th className="text-right">Total</th><th className="text-right">Saldo</th></tr></thead>
            <tbody>
              {datos.map((f) => {
                const vencida = f.estado === 'vigente' && f.dias_vencido > 0
                return (
                  <tr key={f.id} className="hover:bg-tinta-50">
                    <td className="font-mono"><Link to={`/facturas/${f.id}`} className="text-tinta-700 hover:underline">{f.folio}</Link></td>
                    <td>{f.tipo === 'ingreso' ? 'Venta' : 'Compra'}</td>
                    <td>{f.tercero}</td>
                    <td className="whitespace-nowrap">{fecha(f.fecha)}</td>
                    <td className={`whitespace-nowrap ${vencida ? 'font-semibold text-red-700' : ''}`}>{fecha(f.vencimiento)}{vencida && ` (${f.dias_vencido} d)`}</td>
                    <td><Estado valor={f.estado} /></td>
                    <td className="num">{dinero(f.total)} <span className="text-xs text-tinta-400">{f.moneda}</span></td>
                    <td className="num">{f.estado === 'cancelada' ? '—' : dinero(f.saldo)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
