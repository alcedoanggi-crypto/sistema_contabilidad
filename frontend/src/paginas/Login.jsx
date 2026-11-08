import { useState } from 'react'
import { api } from '../api'

const demos = [['admin', 'admin123', 'Administradora'], ['contador', 'contador123', 'Contador'], ['consulta', 'consulta123', 'Solo lectura']]

export default function Login({ onEntrar }) {
  const [usuario, setUsuario] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const entrar = async (e) => {
    e.preventDefault()
    setEnviando(true)
    setError('')
    try { onEntrar(await api('/auth/login', { metodo: 'POST', datos: { usuario, password } })) }
    catch (err) { setError(err.message) }
    finally { setEnviando(false) }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-tinta-900 p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg bg-menta-500 text-lg font-bold text-tinta-900">Σ</div>
          <span className="font-semibold">Sistema de Contabilidad</span>
        </div>
        <div>
          <h1 className="text-4xl font-bold leading-tight">Cada asiento,<br /><span className="text-menta-500">siempre cuadrado.</span></h1>
          <p className="mt-4 max-w-md text-tinta-200">Partida doble validada por la base de datos, libros y estados financieros al instante, cuentas por cobrar y pagar, multimoneda y conciliación bancaria.</p>
          <div className="mt-8 grid max-w-md grid-cols-3 gap-3 text-center text-xs">
            {['Debe = Haber', 'Pólizas inmutables', 'Meses cerrados'].map((t) => (
              <div key={t} className="rounded-lg border border-tinta-700 px-2 py-3 text-tinta-100">{t}</div>
            ))}
          </div>
        </div>
        <p className="text-xs text-tinta-400">Python · FastAPI · PostgreSQL · React</p>
      </div>
      <div className="flex items-center justify-center p-8">
        <form onSubmit={entrar} className="w-full max-w-sm">
          <h2 className="text-2xl font-bold text-tinta-900">Iniciar sesión</h2>
          <p className="mb-6 mt-1 text-sm text-tinta-400">Nexo Soluciones Digitales S.A.</p>
          {error && <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>}
          <label className="etiqueta">Usuario</label>
          <input className="campo mb-4" value={usuario} onChange={(e) => setUsuario(e.target.value)} autoFocus />
          <label className="etiqueta">Contraseña</label>
          <input className="campo mb-6" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button className="btn-primario w-full justify-center py-2.5" disabled={enviando}>{enviando ? 'Entrando…' : 'Entrar'}</button>
          <div className="mt-6 rounded-lg bg-tinta-50 p-3 text-xs text-tinta-600">
            <div className="mb-1.5 font-semibold">Usuarios de demostración</div>
            {demos.map(([u, p, n]) => (
              <button type="button" key={u} onClick={() => { setUsuario(u); setPassword(p) }} className="block hover:underline">
                {n}: <span className="font-mono">{u} / {p}</span>
              </button>
            ))}
          </div>
        </form>
      </div>
    </div>
  )
}
