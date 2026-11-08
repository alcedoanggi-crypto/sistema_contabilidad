import { useState } from 'react'
import { api, dinero, fecha } from '../api'
import { Aviso, Cargando, SelectorCuenta, Titulo, useApi } from '../componentes/ui'

export default function Conciliacion() {
  const bancos = useApi('/bancos')
  const banco = bancos.datos?.[0]
  const movs = useApi(banco ? `/bancos/${banco.id}/movimientos` : null)
  const rep = useApi(banco ? `/bancos/${banco.id}/conciliacion?corte=2026-11-08` : null)
  const [msg, setMsg] = useState({ tipo: 'ok', texto: '' })
  const [elegido, setElegido] = useState(null)       // movimiento bancario seleccionado
  const [registro, setRegistro] = useState(null)     // registrar en libros un cargo que solo está en el banco

  const refrescar = () => { movs.recargar(); rep.recargar(); bancos.recargar() }
  const hacer = async (fn, ok) => {
    setMsg({ tipo: 'ok', texto: '' })
    try { const r = await fn(); setMsg({ tipo: 'ok', texto: typeof ok === 'function' ? ok(r) : ok }); setElegido(null); setRegistro(null); refrescar() }
    catch (e) { setMsg({ tipo: 'error', texto: e.message }) }
  }
  if (bancos.cargando) return <Cargando />
  if (!banco) return <Aviso>No hay cuentas bancarias</Aviso>
  const pendientesBanco = (movs.datos?.banco || []).filter((m) => !m.linea_id)
  const libros = movs.datos?.libros_pendientes || []

  return (
    <>
      <Titulo titulo="Conciliación bancaria" subtitulo={`${banco.banco} ${banco.numero} · ${banco.cuenta}`}>
        <label className="btn-borde cursor-pointer">Importar estado de cuenta (CSV)
          <input type="file" accept=".csv" hidden onChange={(e) => {
            const archivo = e.target.files[0]
            e.target.value = ''
            if (archivo) hacer(() => api(`/bancos/${banco.id}/importar`, { metodo: 'POST', archivo }),
              (r) => `Leídas ${r.leidas} filas: ${r.nuevas} nuevas, ${r.duplicadas} ya importadas`)
          }} /></label>
        <button className="btn-verde" onClick={() => hacer(() => api(`/bancos/${banco.id}/conciliar`, { metodo: 'POST' }), (r) => `${r.emparejados} movimiento(s) emparejados automáticamente`)}>
          Conciliar automáticamente</button>
      </Titulo>
      <Aviso tipo={msg.tipo}>{msg.texto}</Aviso>

      {rep.datos && (
        <div className="mb-5 grid gap-4 md:grid-cols-4">
          {[['Saldo según libros', rep.datos.saldo_libros], ['Saldo según banco', rep.datos.saldo_banco],
            ['Libros conciliado', rep.datos.saldo_libros_conciliado], ['Banco conciliado', rep.datos.saldo_banco_conciliado]].map(([t, v]) => (
            <div key={t} className="tarjeta p-4"><div className="etiqueta">{t}</div><div className="font-mono text-xl font-semibold">{dinero(v)}</div></div>
          ))}
          <div className={`col-span-full rounded-lg px-4 py-2 text-sm font-semibold ${rep.datos.cuadra ? 'bg-menta-100 text-menta-700' : 'bg-amber-100 text-amber-800'}`}>
            {rep.datos.cuadra ? '✓ La conciliación cuadra: las diferencias se explican por las partidas pendientes de abajo' : 'Las partidas pendientes no explican toda la diferencia'}
          </div>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="tarjeta overflow-hidden">
          <div className="px-5 py-3"><h2 className="font-semibold text-tinta-900">Solo en el banco ({pendientesBanco.length})</h2>
            <p className="text-xs text-tinta-400">Elige uno para emparejarlo con un movimiento de libros, o regístralo si falta la póliza (p. ej. comisiones).</p></div>
          <table className="tabla">
            <thead><tr><th>Fecha</th><th>Descripción</th><th className="text-right">Monto</th><th /></tr></thead>
            <tbody>{pendientesBanco.map((m) => (
              <tr key={m.id} className={elegido?.id === m.id ? 'bg-amber-50' : ''}>
                <td className="whitespace-nowrap">{fecha(m.fecha)}</td><td>{m.descripcion}<div className="font-mono text-xs text-tinta-400">{m.referencia}</div></td>
                <td className={`num ${Number(m.monto) < 0 ? 'text-red-700' : ''}`}>{dinero(m.monto)}</td>
                <td className="whitespace-nowrap text-right">
                  <button className="text-xs text-tinta-600 hover:underline" onClick={() => setElegido(elegido?.id === m.id ? null : m)}>{elegido?.id === m.id ? 'cancelar' : 'emparejar'}</button>
                  <button className="ml-2 text-xs text-menta-700 hover:underline" onClick={() => setRegistro({ mov: m, cuenta: null })}>registrar</button>
                </td></tr>))}
              {!pendientesBanco.length && <tr><td colSpan={4} className="py-8 text-center text-tinta-400">Todo conciliado</td></tr>}
            </tbody>
          </table>
          {registro && (
            <div className="border-t border-tinta-100 bg-tinta-50 p-4">
              <div className="mb-2 text-sm">Registrar <b>{registro.mov.descripcion}</b> ({dinero(registro.mov.monto)}) contra la cuenta:</div>
              <div className="flex gap-2">
                <div className="flex-1"><SelectorCuenta valor={registro.cuenta} autoFocus onCambio={(c) => setRegistro({ ...registro, cuenta: c })} /></div>
                <button className="btn-borde" onClick={() => setRegistro(null)}>Cerrar</button>
                <button className="btn-verde" disabled={!registro.cuenta}
                  onClick={() => hacer(() => api(`/bancos/movimientos/${registro.mov.id}/registrar`, { metodo: 'POST', datos: { cuenta_id: registro.cuenta.id } }),
                    (p) => `Póliza ${p.anio}-${String(p.numero).padStart(5, '0')} creada y conciliada`)}>Crear póliza</button>
              </div>
            </div>
          )}
        </div>

        <div className="tarjeta overflow-hidden">
          <div className="px-5 py-3"><h2 className="font-semibold text-tinta-900">Solo en libros ({libros.length})</h2>
            <p className="text-xs text-tinta-400">{elegido ? `Elige el movimiento de ${dinero(elegido.monto)} para emparejar` : 'Partidas en tránsito: registradas en libros que el banco aún no refleja.'}</p></div>
          <table className="tabla">
            <thead><tr><th>Fecha</th><th>Póliza</th><th>Concepto</th><th className="text-right">Monto</th>{elegido && <th />}</tr></thead>
            <tbody>{libros.map((l) => {
              const coincide = elegido && Number(l.monto) === Number(elegido.monto)
              return (
                <tr key={l.linea_id} className={coincide ? 'bg-menta-50' : ''}>
                  <td className="whitespace-nowrap">{fecha(l.fecha)}</td><td className="font-mono">{l.folio}</td><td>{l.concepto}</td>
                  <td className={`num ${Number(l.monto) < 0 ? 'text-red-700' : ''}`}>{dinero(l.monto)}</td>
                  {elegido && <td><button disabled={!coincide} className="text-xs text-menta-700 hover:underline disabled:text-tinta-200"
                    onClick={() => hacer(() => api(`/bancos/movimientos/${elegido.id}/emparejar`, { metodo: 'POST', datos: { linea_id: l.linea_id } }), 'Movimientos emparejados')}>usar</button></td>}
                </tr>)
            })}
              {!libros.length && <tr><td colSpan={5} className="py-8 text-center text-tinta-400">Sin partidas en tránsito</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
