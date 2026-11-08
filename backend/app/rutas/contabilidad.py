"""Sesión, catálogo de cuentas, pólizas, periodos, monedas y tablero."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import esquemas as E
from app.db import fila, filas, get_conn, valor
from app.errores import ErrorNegocio
from app.seguridad import crear_token, puede_escribir, puede_leer, solo_admin, verificar_password
from app.servicios import polizas as srv

router = APIRouter()


# ------------------------------------------------------------------ sesión
@router.post("/auth/login")
def login(datos: E.Login, conn: Connection = Depends(get_conn)):
    u = fila(conn, "SELECT * FROM usuarios WHERE usuario = :u AND activo", u=datos.usuario.strip().lower())
    if u is None or not verificar_password(datos.password, u["password_hash"]):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    return {"token": crear_token(u), "usuario": {"usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"]}}


@router.get("/auth/yo")
def yo(u: dict = Depends(puede_leer)):
    return u


@router.get("/empresa")
def empresa(conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return fila(conn, "SELECT nombre, rfc, moneda_base FROM empresa")


# ------------------------------------------------------------------ catálogo
@router.get("/cuentas")
def cuentas(conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return filas(conn, """SELECT c.*, EXISTS (SELECT 1 FROM poliza_lineas l WHERE l.cuenta_id = c.id) AS tiene_movimientos
                          FROM cuentas c ORDER BY string_to_array(c.codigo, '.')::int[]""")


@router.get("/cuentas/buscar")
def buscar_cuentas(q: str = "", tipo: str | None = None, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    """Autocompletado de la captura de pólizas: solo cuentas de detalle activas."""
    return filas(conn, """
        SELECT id, codigo, nombre, tipo, naturaleza FROM cuentas
         WHERE acepta_movimientos AND activa
           AND (CAST(:tipo AS text) IS NULL OR tipo = :tipo)
           AND (:q = '' OR codigo LIKE :q || '%' OR nombre ILIKE '%' || :q || '%')
         ORDER BY string_to_array(codigo, '.')::int[] LIMIT 25""", q=q.strip(), tipo=tipo)


@router.post("/cuentas", status_code=201)
def crear_cuenta(datos: E.CuentaEntrada, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    tipo, naturaleza = datos.tipo, datos.naturaleza
    if datos.padre_id:
        padre = fila(conn, "SELECT tipo, naturaleza FROM cuentas WHERE id = :id", id=datos.padre_id)
        if padre is None:
            raise ErrorNegocio("VALIDACION", "La cuenta padre no existe")
        tipo, naturaleza = padre["tipo"], naturaleza or padre["naturaleza"]
    if not tipo:
        raise ErrorNegocio("VALIDACION", "Indica el tipo de la cuenta de primer nivel")
    naturaleza = naturaleza or ("deudora" if tipo in ("activo", "gasto") else "acreedora")
    cid = valor(conn, """INSERT INTO cuentas (codigo, nombre, tipo, naturaleza, padre_id)
                         VALUES (:c, :n, :t, :na, :p) RETURNING id""",
                c=datos.codigo.strip(), n=datos.nombre.strip(), t=tipo, na=naturaleza, p=datos.padre_id)
    return fila(conn, "SELECT * FROM cuentas WHERE id = :id", id=cid)


@router.put("/cuentas/{cuenta_id}")
def editar_cuenta(cuenta_id: int, datos: E.CuentaEdicion, conn: Connection = Depends(get_conn),
                  _: dict = Depends(puede_escribir)):
    conn.execute(text("UPDATE cuentas SET nombre = :n, activa = :a WHERE id = :id"),
                 {"n": datos.nombre.strip(), "a": datos.activa, "id": cuenta_id})
    return fila(conn, "SELECT * FROM cuentas WHERE id = :id", id=cuenta_id)


# ------------------------------------------------------------------ pólizas
@router.get("/polizas")
def listar_polizas(desde: date | None = None, hasta: date | None = None, estado: str | None = None, q: str | None = None,
                   conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return srv.listar(conn, desde, hasta, estado, q)


@router.get("/polizas/{poliza_id}")
def ver_poliza(poliza_id: int, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return srv.obtener(conn, poliza_id)


@router.post("/polizas", status_code=201)
def crear_poliza(datos: E.PolizaEntrada, conn: Connection = Depends(get_conn), u: dict = Depends(puede_escribir)):
    return srv.crear_poliza(conn, datos.model_dump(), u["usuario"])


@router.put("/polizas/{poliza_id}")
def editar_poliza(poliza_id: int, datos: E.PolizaEntrada, conn: Connection = Depends(get_conn),
                  u: dict = Depends(puede_escribir)):
    return srv.actualizar_borrador(conn, poliza_id, datos.model_dump(), u["usuario"])


@router.delete("/polizas/{poliza_id}", status_code=204)
def borrar_poliza(poliza_id: int, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    srv.eliminar_borrador(conn, poliza_id)


@router.post("/polizas/{poliza_id}/contabilizar")
def contabilizar(poliza_id: int, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    return srv.contabilizar(conn, poliza_id)


@router.post("/polizas/{poliza_id}/revertir")
def revertir(poliza_id: int, datos: E.Reversa, conn: Connection = Depends(get_conn), u: dict = Depends(puede_escribir)):
    return srv.revertir(conn, poliza_id, datos.fecha, datos.motivo, u["usuario"])


# ------------------------------------------------------------------ periodos
@router.get("/periodos")
def periodos(conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return filas(conn, """
        SELECT pe.*, (SELECT count(*) FROM polizas p WHERE extract(year FROM p.fecha) = pe.anio
                        AND extract(month FROM p.fecha) = pe.mes AND p.estado <> 'borrador') AS polizas,
               (SELECT count(*) FROM polizas p WHERE extract(year FROM p.fecha) = pe.anio
                        AND extract(month FROM p.fecha) = pe.mes AND p.estado = 'borrador') AS borradores
          FROM periodos pe ORDER BY anio DESC, mes DESC""")


@router.post("/periodos/{anio}/{mes}/cerrar")
def cerrar(anio: int, mes: int, conn: Connection = Depends(get_conn), u: dict = Depends(puede_escribir)):
    return fila(conn, "SELECT * FROM cerrar_periodo(:a, :m, :u)", a=anio, m=mes, u=u["usuario"])


@router.post("/periodos/{anio}/{mes}/reabrir")
def reabrir(anio: int, mes: int, datos: E.Reapertura, conn: Connection = Depends(get_conn), u: dict = Depends(solo_admin)):
    return fila(conn, "SELECT * FROM reabrir_periodo(:a, :m, :u, :mo)", a=anio, m=mes, u=u["usuario"], mo=datos.motivo)


# ------------------------------------------------------------------ monedas
@router.get("/monedas")
def monedas(conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    lista = filas(conn, "SELECT * FROM monedas ORDER BY codigo")
    for m in lista:
        m["ultimo"] = fila(conn, "SELECT fecha, tasa FROM tipos_cambio WHERE moneda = :m ORDER BY fecha DESC LIMIT 1",
                           m=m["codigo"])
    return lista


@router.get("/tipos-cambio")
def tipos_cambio(moneda: str | None = None, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return filas(conn, """SELECT * FROM tipos_cambio WHERE (CAST(:m AS text) IS NULL OR moneda = :m)
                          ORDER BY fecha DESC, moneda LIMIT 200""", m=moneda)


@router.get("/tipos-cambio/vigente")
def tipo_cambio_vigente(moneda: str, fecha: date, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return {"moneda": moneda, "fecha": fecha, "tasa": valor(conn, "SELECT tipo_cambio_en(:m, :f)", m=moneda, f=fecha)}


@router.post("/tipos-cambio", status_code=201)
def guardar_tipo_cambio(datos: E.TipoCambioEntrada, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    return fila(conn, """INSERT INTO tipos_cambio (moneda, fecha, tasa) VALUES (:m, :f, :t)
                         ON CONFLICT (moneda, fecha) DO UPDATE SET tasa = EXCLUDED.tasa RETURNING *""",
                m=datos.moneda.upper(), f=datos.fecha, t=datos.tasa)


# ------------------------------------------------------------------ tablero
@router.get("/tablero")
def tablero(hoy: date | None = None, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    hoy = hoy or valor(conn, "SELECT coalesce(max(fecha), current_date) FROM polizas WHERE estado <> 'borrador'")
    inicio_mes, inicio_anio = hoy.replace(day=1), hoy.replace(month=1, day=1)
    er_mes = fila(conn, """SELECT coalesce(sum(importe) FILTER (WHERE tipo = 'ingreso' AND acepta_movimientos), 0) AS ingresos,
                                  coalesce(sum(importe) FILTER (WHERE tipo = 'gasto' AND acepta_movimientos), 0) AS gastos
                             FROM estado_resultados(:d, :h)""", d=inicio_mes, h=hoy)
    bancos = filas(conn, """SELECT b.id, b.nombre, b.banco, b.moneda,
                                   coalesce((SELECT sum(debe_base - haber_base) FROM v_movimientos m
                                              WHERE m.cuenta_id = b.cuenta_id AND m.fecha <= :h), 0) AS saldo
                              FROM cuentas_bancarias b ORDER BY b.id""", h=hoy)
    cxc = fila(conn, "SELECT coalesce(sum(total), 0) AS total, coalesce(sum(total - coalesce(por_vencer, 0)), 0) AS vencido "
                     "FROM antiguedad_saldos('cxc', :h)", h=hoy)
    cxp = fila(conn, "SELECT coalesce(sum(total), 0) AS total, coalesce(sum(total - coalesce(por_vencer, 0)), 0) AS vencido "
                     "FROM antiguedad_saldos('cxp', :h)", h=hoy)
    meses = filas(conn, """
        SELECT to_char(date_trunc('month', m.fecha), 'YYYY-MM') AS mes,
               coalesce(sum(m.haber_base - m.debe_base) FILTER (WHERE c.tipo = 'ingreso'), 0) AS ingresos,
               coalesce(sum(m.debe_base - m.haber_base) FILTER (WHERE c.tipo = 'gasto'), 0) AS gastos
          FROM v_movimientos m JOIN cuentas c ON c.id = m.cuenta_id
         WHERE m.fecha > (date_trunc('month', CAST(:h AS date)) - interval '6 months') AND m.fecha <= :h
         GROUP BY 1 ORDER BY 1""", h=hoy)
    return {
        "fecha": hoy,
        "ingresos_mes": er_mes["ingresos"], "gastos_mes": er_mes["gastos"],
        "utilidad_mes": er_mes["ingresos"] - er_mes["gastos"],
        "utilidad_anio": valor(conn, "SELECT utilidad_periodo(:d, :h)", d=inicio_anio, h=hoy),
        "bancos": bancos, "saldo_bancos": sum((b["saldo"] for b in bancos), Decimal("0")),
        "cxc": cxc, "cxp": cxp, "meses": meses,
        "borradores": valor(conn, "SELECT count(*) FROM polizas WHERE estado = 'borrador'"),
        "pendientes_conciliar": valor(conn, "SELECT count(*) FROM movimientos_banco WHERE linea_id IS NULL"),
        "recientes": srv.listar(conn, None, None, None, None, limite=6),
    }
