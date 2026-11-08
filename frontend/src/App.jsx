import { useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { sesion } from './api'
import Login from './paginas/Login'
import Tablero from './paginas/Tablero'
import Cuentas from './paginas/Cuentas'
import Polizas from './paginas/Polizas'
import PolizaForm from './paginas/PolizaForm'
import PolizaDetalle from './paginas/PolizaDetalle'
import Facturas from './paginas/Facturas'
import FacturaForm from './paginas/FacturaForm'
import FacturaDetalle from './paginas/FacturaDetalle'
import Reportes from './paginas/Reportes'
import Conciliacion from './paginas/Conciliacion'
import Periodos from './paginas/Periodos'

const menu = [
  ['/', 'Inicio', 'M3 12l9-8 9 8M5 10v10h14V10'],
  ['/polizas', 'Pólizas', 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6'],
  ['/facturas', 'Facturas', 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6'],
  ['/reportes', 'Reportes', 'M4 20V10M10 20V4M16 20v-7M22 20H2'],
  ['/conciliacion', 'Conciliación', 'M3 10h18M5 10V20h14V10M3 10l9-6 9 6M9 14v3M15 14v3'],
  ['/cuentas', 'Catálogo', 'M4 6h16M4 12h10M4 18h7'],
  ['/periodos', 'Periodos', 'M7 3v3M17 3v3M4 8h16M5 5h14v16H5z'],
]

function Icono({ d }) {
  return <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
}

function Marco({ usuario, onSalir, children }) {
  return (
    <div className="flex min-h-screen">
      <aside className="no-imprimir sticky top-0 flex h-screen w-60 shrink-0 flex-col bg-tinta-900 text-tinta-100">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-menta-500 font-bold text-tinta-900">Σ</div>
          <div>
            <div className="text-sm font-bold text-white">Contabilidad</div>
            <div className="text-xs text-tinta-400">Nexo Soluciones</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {menu.map(([ruta, nombre, d]) => (
            <NavLink key={ruta} to={ruta} end={ruta === '/'}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${isActive ? 'bg-tinta-700 text-white' : 'text-tinta-200 hover:bg-tinta-800'}`}>
              <Icono d={d} />{nombre}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-tinta-800 px-5 py-4 text-xs">
          <div className="font-semibold text-white">{usuario.nombre}</div>
          <div className="text-tinta-400">Rol: {usuario.rol}</div>
          <button onClick={onSalir} className="mt-2 text-menta-500 hover:underline">Cerrar sesión</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6 lg:p-8">{children}</main>
    </div>
  )
}

export default function App() {
  const [s, setS] = useState(sesion.obtener())
  const navegar = useNavigate()
  if (!s) {
    return (
      <Routes>
        <Route path="*" element={<Login onEntrar={(nueva) => { sesion.guardar(nueva); setS(nueva); navegar('/') }} />} />
      </Routes>
    )
  }
  return (
    <Marco usuario={s.usuario} onSalir={() => { sesion.cerrar(); setS(null); navegar('/login') }}>
      <Routes>
        <Route path="/" element={<Tablero />} />
        <Route path="/polizas" element={<Polizas />} />
        <Route path="/polizas/nueva" element={<PolizaForm />} />
        <Route path="/polizas/:id/editar" element={<PolizaForm />} />
        <Route path="/polizas/:id" element={<PolizaDetalle />} />
        <Route path="/facturas" element={<Facturas />} />
        <Route path="/facturas/nueva" element={<FacturaForm />} />
        <Route path="/facturas/:id" element={<FacturaDetalle />} />
        <Route path="/reportes" element={<Reportes />} />
        <Route path="/conciliacion" element={<Conciliacion />} />
        <Route path="/cuentas" element={<Cuentas />} />
        <Route path="/periodos" element={<Periodos />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </Marco>
  )
}
