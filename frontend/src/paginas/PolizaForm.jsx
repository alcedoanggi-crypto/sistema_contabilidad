import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, centavos, deCentavos, dinero, hoy } from '../api'
import { Aviso, Cargando, SelectorCuenta, Titulo } from '../componentes/ui'

const lineaVacia = () => ({ clave: crypto.randomUUID(), cuenta: null, descripcion: '', debe: '', haber: '' })

export default function PolizaForm() {
  const { id } = useParams()
  const navegar = useNavigate()
  const [cab, setCab] = useState({ tipo: 'diario', fecha: hoy(), concepto: '', moneda: 'USD', tipo_cambio: '' })
  const [lineas, setLineas] = useState([lineaVacia(), lineaVacia()])
  const [monedas, setMonedas] = useState([])
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [cargando, setCargando] = useState(Boolean(id))
  const tabla = useRef(null)

  useEffect(() => { api('/monedas').then(setMonedas) }, [])
  useEffect(() => {
    if (!id) return
    api(`/polizas/${id}`).then((p) => {
      setCab({ tipo: p.tipo, fecha: p.fecha, concepto: p.concepto, moneda: p.moneda, tipo_cambio: p.moneda === 'USD' ? '' : p.tipo_cambio })
      setLineas(p.lineas.map((l) => ({ clave: crypto.randomUUID(), cuenta: { id: l.cuenta_id, codigo: l.cuenta_codigo, nombre: l.cuenta_nombre },
        descripcion: l.descripcion || '', debe: Number(l.debe) ? l.debe : '', haber: Number(l.haber) ? l.haber : '' })))
      setCargando(false)
    }).catch((e) => { setError(e.message); setCargando(false) })
  }, [id])
  // Al cambiar de moneda se propone el tipo de cambio vigente en la fecha
  useEffect(() => {
    if (cab.moneda === 'USD') return setCab((c) => ({ ...c, tipo_cambio: '' }))
    api(`/tipos-cambio/vigente?moneda=${cab.moneda}&fecha=${cab.fecha}`).then((r) => setCab((c) => ({ ...c, tipo_cambio: r.tasa })))
      .catch((e) => setError(e.message))
  }, [cab.moneda, cab.fecha])

  const totalDebe = lineas.reduce((s, l) => s + centavos(l.debe), 0)
  const totalHaber = lineas.reduce((s, l) => s + centavos(l.haber), 0)
  const diferencia = totalDebe - totalHaber
  const cuadra = diferencia === 0 && totalDebe > 0

  const cambiar = (i, campo, valor) => setLineas((ls) => ls.map((l, k) => {
    if (k !== i) return l
    const n = { ...l, [campo]: valor }
    if (campo === 'debe' && valor) n.haber = ''       // una línea es cargo O abono
    if (campo === 'haber' && valor) n.debe = ''
    return n
  }))
  const agregar = () => {
    setLineas((ls) => [...ls, lineaVacia()])
    setTimeout(() => tabla.current?.querySelector('tbody tr:last-child input')?.focus(), 30)
  }
  // Enter en el último importe de la última fila agrega una fila nueva
  const alEnter = (e, i) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (i === lineas.length - 1) agregar()
    else tabla.current?.querySelectorAll('tbody tr')[i + 1]?.querySelector('input')?.focus()
  }
  // Atajo: completa el importe que falta para cuadrar
  const cuadrar = (i) => {
    const l = lineas[i]
    const sinEsta = diferencia - centavos(l.debe) + centavos(l.haber)
    if (sinEsta > 0) cambiar(i, 'haber', deCentavos(sinEsta))
    else if (sinEsta < 0) cambiar(i, 'debe', deCentavos(-sinEsta))
  }

  const guardar = async (contabilizar) => {
    setError('')
    const validas = lineas.filter((l) => l.cuenta || centavos(l.debe) || centavos(l.haber))
    if (validas.some((l) => !l.cuenta)) return setError('Hay líneas con importe pero sin cuenta')
    setGuardando(true)
    const datos = {
      ...cab, tipo_cambio: cab.tipo_cambio || null, contabilizar,
      lineas: validas.map((l) => ({ cuenta_id: l.cuenta.id, descripcion: l.descripcion || null,
        debe: deCentavos(centavos(l.debe)), haber: deCentavos(centavos(l.haber)) })),
    }
    try {
      const p = await api(id ? `/polizas/${id}` : '/polizas', { metodo: id ? 'PUT' : 'POST', datos })
      navegar(`/polizas/${p.id}`)
    } catch (e) { setError(e.message); setGuardando(false) }
  }

  useEffect(() => {
    const atajo = (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); if (cuadra) guardar(true) } }
    window.addEventListener('keydown', atajo)
    return () => window.removeEventListener('keydown', atajo)
  })

  if (cargando) return <Cargando />
  return (
    <>
      <Titulo titulo={id ? 'Editar borrador' : 'Nueva póliza'} subtitulo="Enter avanza · Ctrl+S contabiliza · «=» completa el importe que falta" />
      <Aviso>{error}</Aviso>
      <div className="tarjeta mb-4 grid gap-4 p-5 md:grid-cols-6">
        <div><label className="etiqueta">Tipo</label>
          <select className="campo" value={cab.tipo} onChange={(e) => setCab({ ...cab, tipo: e.target.value })}>
            <option value="diario">Diario</option><option value="ingreso">Ingreso</option><option value="egreso">Egreso</option>
          </select></div>
        <div><label className="etiqueta">Fecha</label>
          <input type="date" className="campo" value={cab.fecha} onChange={(e) => setCab({ ...cab, fecha: e.target.value })} /></div>
        <div className="md:col-span-2"><label className="etiqueta">Concepto</label>
          <input className="campo" value={cab.concepto} autoFocus onChange={(e) => setCab({ ...cab, concepto: e.target.value })} placeholder="Ej. Pago de nómina quincenal" /></div>
        <div><label className="etiqueta">Moneda</label>
          <select className="campo" value={cab.moneda} onChange={(e) => setCab({ ...cab, moneda: e.target.value })}>
            {monedas.map((m) => <option key={m.codigo} value={m.codigo}>{m.codigo}</option>)}
          </select></div>
        <div><label className="etiqueta">Tipo de cambio</label>
          <input className="campo font-mono" disabled={cab.moneda === 'USD'} value={cab.moneda === 'USD' ? '1' : cab.tipo_cambio}
            onChange={(e) => setCab({ ...cab, tipo_cambio: e.target.value })} /></div>
      </div>

      <div className="tarjeta overflow-visible">
        <table className="tabla" ref={tabla}>
          <thead><tr><th className="w-10">#</th><th className="w-80">Cuenta</th><th>Descripción</th><th className="w-36 text-right">Debe</th><th className="w-36 text-right">Haber</th><th className="w-20" /></tr></thead>
          <tbody>
            {lineas.map((l, i) => (
              <tr key={l.clave}>
                <td className="text-tinta-400">{i + 1}</td>
                <td><SelectorCuenta valor={l.cuenta} onCambio={(c) => cambiar(i, 'cuenta', c)} /></td>
                <td><input className="campo" value={l.descripcion} onChange={(e) => cambiar(i, 'descripcion', e.target.value)} /></td>
                <td><input className="campo num" inputMode="decimal" value={l.debe} onKeyDown={(e) => { if (e.key === '=') { e.preventDefault(); cuadrar(i) } }}
                  onChange={(e) => cambiar(i, 'debe', e.target.value.replace(/[^\d.]/g, ''))} /></td>
                <td><input className="campo num" inputMode="decimal" value={l.haber} onKeyDown={(e) => { if (e.key === '=') { e.preventDefault(); cuadrar(i) } else alEnter(e, i) }}
                  onChange={(e) => cambiar(i, 'haber', e.target.value.replace(/[^\d.]/g, ''))} /></td>
                <td className="whitespace-nowrap text-right">
                  <button title="Completar para cuadrar" onClick={() => cuadrar(i)} className="px-1.5 text-tinta-400 hover:text-tinta-700">=</button>
                  <button title="Quitar línea" disabled={lineas.length <= 2} onClick={() => setLineas((ls) => ls.filter((_, k) => k !== i))}
                    className="px-1.5 text-tinta-400 hover:text-red-600 disabled:opacity-30">✕</button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-tinta-50 font-semibold">
              <td colSpan={3} className="px-3 py-2"><button onClick={agregar} className="text-sm text-tinta-600 hover:underline">+ Agregar línea</button></td>
              <td className="num px-3">{dinero(totalDebe / 100)}</td><td className="num px-3">{dinero(totalHaber / 100)}</td><td />
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className={`rounded-lg px-4 py-2 text-sm font-semibold ${cuadra ? 'bg-menta-100 text-menta-700' : 'bg-amber-100 text-amber-800'}`}>
          {cuadra ? '✓ La póliza cuadra' : totalDebe === 0 ? 'Captura los importes' : `Diferencia: ${dinero(Math.abs(diferencia) / 100)} en el ${diferencia > 0 ? 'haber' : 'debe'}`}
        </div>
        <div className="flex gap-2">
          <button className="btn-borde" onClick={() => navegar(-1)}>Cancelar</button>
          <button className="btn-borde" disabled={guardando || !cab.concepto} onClick={() => guardar(false)}>Guardar borrador</button>
          <button className="btn-verde" disabled={guardando || !cuadra || !cab.concepto} onClick={() => guardar(true)}>Contabilizar</button>
        </div>
      </div>
    </>
  )
}
