import { Link } from 'react-router-dom'
import { dinero, fecha } from '../api'
import { Aviso, Cargando, Estado, Titulo, useApi } from '../componentes/ui'

function Kpi({ titulo, valor, nota, color = 'text-tinta-900' }) {
  return (
    <div className="tarjeta p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-tinta-400">{titulo}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${color}`}>{dinero(valor)}</div>
      {nota && <div className="mt-1 text-xs text-tinta-400">{nota}</div>}
    </div>
  )
}

export default function Tablero() {
  const { datos: d, error, cargando } = useApi('/tablero')
  if (cargando) return <Cargando />
  if (error) return <Aviso>{error}</Aviso>
  const maximo = Math.max(1, ...d.meses.flatMap((m) => [Number(m.ingresos), Number(m.gastos)]))

  return (
    <>
      <Titulo titulo="Resumen" subtitulo={`Cifras en USD al ${fecha(d.fecha)}`}>
        <Link to="/polizas/nueva" className="btn-primario">+ Nueva póliza</Link>
        <Link to="/facturas/nueva" className="btn-borde">+ Nueva factura</Link>
      </Titulo>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi titulo="Saldo en bancos" valor={d.saldo_bancos} nota={d.bancos.map((b) => b.banco).join(', ')} />
        <Kpi titulo="Utilidad del año" valor={d.utilidad_anio} color={Number(d.utilidad_anio) >= 0 ? 'text-menta-700' : 'text-red-700'} />
        <Kpi titulo="Por cobrar" valor={d.cxc.total} nota={`${dinero(d.cxc.vencido)} vencido`} />
        <Kpi titulo="Por pagar" valor={d.cxp.total} nota={`${dinero(d.cxp.vencido)} vencido`} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="tarjeta p-5 xl:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-tinta-900">Ingresos vs gastos por mes</h2>
            <div className="flex gap-4 text-xs text-tinta-400">
              <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-menta-500" />Ingresos</span>
              <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-tinta-400" />Gastos</span>
            </div>
          </div>
          <div className="flex h-56 items-end gap-6 border-b border-tinta-100 px-2">
            {d.meses.map((m) => (
              <div key={m.mes} className="flex flex-1 flex-col items-center gap-1">
                <div className="flex h-48 w-full items-end justify-center gap-1.5">
                  {[['ingresos', 'bg-menta-500'], ['gastos', 'bg-tinta-400']].map(([k, c]) => (
                    <div key={k} title={`${k}: ${dinero(m[k])}`} className={`w-1/3 max-w-10 rounded-t ${c}`}
                      style={{ height: `${(Number(m[k]) / maximo) * 100}%` }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-6 px-2 pt-2">
            {d.meses.map((m) => <div key={m.mes} className="flex-1 text-center text-xs text-tinta-400">{m.mes}</div>)}
          </div>
        </div>

        <div className="tarjeta p-5">
          <h2 className="mb-3 font-semibold text-tinta-900">Este mes</h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt>Ingresos</dt><dd className="font-mono">{dinero(d.ingresos_mes)}</dd></div>
            <div className="flex justify-between"><dt>Gastos</dt><dd className="font-mono">{dinero(d.gastos_mes)}</dd></div>
            <div className="flex justify-between border-t border-tinta-100 pt-2 font-semibold"><dt>Resultado</dt><dd className="font-mono">{dinero(d.utilidad_mes)}</dd></div>
          </dl>
          <h2 className="mb-2 mt-6 font-semibold text-tinta-900">Pendientes</h2>
          <ul className="space-y-1.5 text-sm">
            <li><Link to="/polizas?estado=borrador" className="hover:underline">{d.borradores} póliza(s) en borrador</Link></li>
            <li><Link to="/conciliacion" className="hover:underline">{d.pendientes_conciliar} movimiento(s) bancario(s) sin conciliar</Link></li>
            <li><Link to="/reportes?r=antiguedad" className="hover:underline">{dinero(d.cxc.vencido)} USD de clientes vencido</Link></li>
          </ul>
        </div>
      </div>

      <div className="tarjeta mt-6 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3">
          <h2 className="font-semibold text-tinta-900">Últimas pólizas</h2>
          <Link to="/polizas" className="text-sm text-tinta-600 hover:underline">Ver todas</Link>
        </div>
        <table className="tabla">
          <thead><tr><th>Folio</th><th>Fecha</th><th>Concepto</th><th>Estado</th><th className="text-right">Importe</th></tr></thead>
          <tbody>
            {d.recientes.map((p) => (
              <tr key={p.id} className="hover:bg-tinta-50">
                <td className="font-mono"><Link to={`/polizas/${p.id}`} className="text-tinta-700 hover:underline">{p.folio || 'borrador'}</Link></td>
                <td>{fecha(p.fecha)}</td><td>{p.concepto}</td><td><Estado valor={p.estado} /></td>
                <td className="num">{dinero(p.total)} <span className="text-xs text-tinta-400">{p.moneda}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
