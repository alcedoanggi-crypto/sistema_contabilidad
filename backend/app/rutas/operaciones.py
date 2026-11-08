"""Terceros, impuestos, facturas, pagos y bancos (conciliación)."""
from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import esquemas as E
from app.db import fila, filas, get_conn, valor
from app.errores import ErrorNegocio
from app.seguridad import puede_escribir, puede_leer, solo_admin
from app.servicios import conciliacion as conc
from app.servicios import facturas as srv_fact

router = APIRouter()


# ------------------------------------------------------------------ terceros
@router.get("/terceros")
def terceros(tipo: str | None = None, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return filas(conn, """SELECT * FROM terceros WHERE (CAST(:t AS text) IS NULL OR tipo = :t OR tipo = 'ambos')
                          ORDER BY nombre""", t=tipo)


@router.post("/terceros", status_code=201)
def crear_tercero(datos: E.TerceroEntrada, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    return fila(conn, """INSERT INTO terceros (tipo, nombre, rfc, email, telefono, dias_credito, activo)
                         VALUES (:tipo, :nombre, :rfc, :email, :telefono, :dias_credito, :activo) RETURNING *""",
                **datos.model_dump())


@router.put("/terceros/{tercero_id}")
def editar_tercero(tercero_id: int, datos: E.TerceroEntrada, conn: Connection = Depends(get_conn),
                   _: dict = Depends(puede_escribir)):
    return fila(conn, """UPDATE terceros SET tipo=:tipo, nombre=:nombre, rfc=:rfc, email=:email, telefono=:telefono,
                                dias_credito=:dias_credito, activo=:activo WHERE id = :id RETURNING *""",
                id=tercero_id, **datos.model_dump())


# ------------------------------------------------------------------ impuestos
@router.get("/impuestos")
def impuestos(conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return filas(conn, """SELECT i.*, cv.codigo || ' ' || cv.nombre AS cuenta_ventas, cc.codigo || ' ' || cc.nombre AS cuenta_compras
                            FROM impuestos i JOIN cuentas cv ON cv.id = i.cuenta_ventas_id JOIN cuentas cc ON cc.id = i.cuenta_compras_id
                           ORDER BY i.tipo DESC, i.codigo""")


@router.put("/impuestos/{impuesto_id}")
def editar_impuesto(impuesto_id: int, datos: E.ImpuestoEdicion, conn: Connection = Depends(get_conn),
                    _: dict = Depends(solo_admin)):
    return fila(conn, "UPDATE impuestos SET nombre=:n, tasa=:t, activo=:a WHERE id=:id RETURNING *",
                n=datos.nombre, t=datos.tasa, a=datos.activo, id=impuesto_id)


# ------------------------------------------------------------------ facturas
@router.get("/facturas")
def facturas(tipo: str | None = None, estado: str | None = None, q: str | None = None,
             conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return srv_fact.listar(conn, tipo, estado, q)


@router.post("/facturas/calcular")
def calcular(datos: E.FacturaEntrada, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    """Vista previa de totales mientras se captura (no guarda nada)."""
    imps = [fila(conn, "SELECT * FROM impuestos WHERE codigo = :c", c=c) for c in datos.impuestos]
    t = srv_fact.calcular_totales([l.model_dump() for l in datos.lineas], [i for i in imps if i])
    return {k: v for k, v in t.items() if k != "impuestos"} | {
        "impuestos": [{"codigo": i["codigo"], "nombre": i["nombre"], "tipo": i["tipo"], "importe": i["importe"]} for i in t["impuestos"]]}


@router.get("/facturas/{factura_id}")
def ver_factura(factura_id: int, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return srv_fact.obtener(conn, factura_id)


@router.post("/facturas", status_code=201)
def crear_factura(datos: E.FacturaEntrada, conn: Connection = Depends(get_conn), u: dict = Depends(puede_escribir)):
    return srv_fact.crear_factura(conn, datos.model_dump(), u["usuario"])


@router.post("/facturas/{factura_id}/pagos", status_code=201)
def pagar(factura_id: int, datos: E.PagoEntrada, conn: Connection = Depends(get_conn), u: dict = Depends(puede_escribir)):
    return srv_fact.registrar_pago(conn, factura_id, datos.model_dump(), u["usuario"])


@router.post("/facturas/{factura_id}/cancelar")
def cancelar(factura_id: int, datos: E.Reversa, conn: Connection = Depends(get_conn), u: dict = Depends(puede_escribir)):
    return srv_fact.cancelar_factura(conn, factura_id, datos.fecha, datos.motivo, u["usuario"])


# ------------------------------------------------------------------ bancos
@router.get("/bancos")
def bancos(conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return filas(conn, """
        SELECT b.*, c.codigo || ' ' || c.nombre AS cuenta,
               (SELECT count(*) FROM movimientos_banco mb WHERE mb.cuenta_bancaria_id = b.id AND mb.linea_id IS NULL) AS pendientes,
               (SELECT count(*) FROM movimientos_banco mb WHERE mb.cuenta_bancaria_id = b.id) AS movimientos
          FROM cuentas_bancarias b JOIN cuentas c ON c.id = b.cuenta_id ORDER BY b.id""")


@router.post("/bancos/{banco_id}/importar")
async def importar(banco_id: int, archivo: UploadFile = File(...), conn: Connection = Depends(get_conn),
                   _: dict = Depends(puede_escribir)):
    contenido = await archivo.read()
    if len(contenido) > 2_000_000:
        raise ErrorNegocio("VALIDACION", "El archivo supera 2 MB")
    return conc.importar(conn, banco_id, archivo.filename or "estado_cuenta.csv", contenido)


@router.get("/bancos/{banco_id}/movimientos")
def movimientos(banco_id: int, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return {"banco": conc.movimientos_banco(conn, banco_id), "libros_pendientes": conc.lineas_libros_pendientes(conn, banco_id)}


@router.post("/bancos/{banco_id}/conciliar")
def conciliar(banco_id: int, tolerancia: int = 3, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    return conc.conciliar_automatico(conn, banco_id, tolerancia)


@router.post("/bancos/movimientos/{movimiento_id}/emparejar")
def emparejar(movimiento_id: int, datos: E.Emparejar, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    return conc.emparejar_manual(conn, movimiento_id, datos.linea_id)


@router.delete("/bancos/movimientos/{movimiento_id}/emparejar", status_code=204)
def desemparejar(movimiento_id: int, conn: Connection = Depends(get_conn), _: dict = Depends(puede_escribir)):
    conc.desemparejar(conn, movimiento_id)


@router.post("/bancos/movimientos/{movimiento_id}/registrar")
def registrar(movimiento_id: int, datos: E.RegistroDesdeBanco, conn: Connection = Depends(get_conn),
              u: dict = Depends(puede_escribir)):
    return conc.registrar_desde_banco(conn, movimiento_id, datos.cuenta_id, datos.concepto, u["usuario"])


@router.get("/bancos/{banco_id}/conciliacion")
def reporte(banco_id: int, corte: date, conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    return conc.reporte(conn, banco_id, corte)
