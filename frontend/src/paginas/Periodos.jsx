import { useState } from 'react'
import { api, sesion } from '../api'
import { Aviso, Cargando, Estado, Titulo, useApi } from '../componentes/ui'

const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']

export default function Periodos() {
  const { datos, error, cargando, recargar } = useApi('/periodos')
  const [msg, setMsg] = useState({ tipo: 'ok', texto: '' })
  const esAdmin = sesion.obtener()?.usuario.rol === 'admin'

  const hacer = async (ruta, datos, ok) => {
    setMsg({ tipo: 'ok', texto: '' })
    try { await api(ruta, { metodo: 'POST', datos }); setMsg({ tipo: 'ok', texto: ok }); recargar() }
    catch (e) { setMsg({ tipo: 'error', texto: e.message }) }
  }
  if (cargando) return <Cargando />
  return (
    <>
      <Titulo titulo="Periodos contables" subtitulo="Un mes cerrado bloquea cualquier alta, cambio o reversa con fecha de ese mes (lo impide la base de datos)" />
      <Aviso tipo={msg.tipo}>{error || msg.texto}</Aviso>
      <div className="tarjeta overflow-hidden">
        <table className="tabla">
          <thead><tr><th>Periodo</th><th>Estado</th><th className="text-right">Pólizas</th><th className="text-right">Borradores</th><th>Cerrado por</th><th /></tr></thead>
          <tbody>{datos.map((p) => (
            <tr key={p.id}>
              <td className="font-medium">{MESES[p.mes - 1]} {p.anio}</td>
              <td><Estado valor={p.estado} /></td>
              <td className="num">{p.polizas}</td>
              <td className={`num ${p.borradores ? 'font-semibold text-amber-700' : ''}`}>{p.borradores}</td>
              <td className="text-tinta-600">{p.cerrado_por}</td>
              <td className="text-right">
                {p.estado === 'abierto'
                  ? <button className="btn-borde py-1" onClick={() => hacer(`/periodos/${p.anio}/${p.mes}/cerrar`, undefined, `${MESES[p.mes - 1]} cerrado`)}>Cerrar mes</button>
                  : esAdmin && <button className="btn-peligro py-1" onClick={() => {
                    const motivo = window.prompt('Motivo de la reapertura')
                    if (motivo) hacer(`/periodos/${p.anio}/${p.mes}/reabrir`, { motivo }, `${MESES[p.mes - 1]} reabierto`)
                  }}>Reabrir</button>}
              </td>
            </tr>))}
          </tbody>
        </table>
      </div>
    </>
  )
}
