// Cliente de la API. Los montos llegan como texto ("1234.50") para no perder centavos;
// solo se convierten a número para mostrarlos o sumarlos en pantalla.

const clave = 'contab_sesion'

export const sesion = {
  obtener: () => { try { return JSON.parse(localStorage.getItem(clave)) } catch { return null } },
  guardar: (s) => localStorage.setItem(clave, JSON.stringify(s)),
  cerrar: () => localStorage.removeItem(clave),
}

export async function api(ruta, { metodo = 'GET', datos, archivo } = {}) {
  const s = sesion.obtener()
  const headers = s ? { Authorization: `Bearer ${s.token}` } : {}
  let body
  if (archivo) { body = new FormData(); body.append('archivo', archivo) }
  else if (datos !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(datos) }
  const r = await fetch(`/api${ruta}`, { method: metodo, headers, body })
  if (r.status === 401 && s) { sesion.cerrar(); window.location.href = '/login' }
  if (r.status === 204) return null
  const json = await r.json().catch(() => ({}))
  if (!r.ok) {
    const det = Array.isArray(json.detail) ? json.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join(' · ') : json.detail
    throw new Error(det || `Error ${r.status}`)
  }
  return json
}

export async function descargar(ruta, nombre) {
  const s = sesion.obtener()
  const r = await fetch(`/api${ruta}`, { headers: { Authorization: `Bearer ${s?.token}` } })
  if (!r.ok) throw new Error('No se pudo generar el archivo')
  const url = URL.createObjectURL(await r.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: nombre })
  a.click()
  URL.revokeObjectURL(url)
}

const fmt = new Intl.NumberFormat('es-MX', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const dinero = (v) => (v === null || v === undefined || v === '' ? '' : fmt.format(Number(v)))
export const fecha = (v) => (v ? new Date(v + 'T00:00:00').toLocaleDateString('es-MX', { day: '2-digit', month: 'short', year: 'numeric' }) : '')
export const hoy = () => new Date().toISOString().slice(0, 10)

// Suma exacta de montos con 2 decimales usando centavos enteros
export const centavos = (v) => Math.round(Number(v || 0) * 100)
export const deCentavos = (c) => (c / 100).toFixed(2)
