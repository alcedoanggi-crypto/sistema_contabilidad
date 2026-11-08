"""Facturas de ingreso (ventas) y de gasto (compras) con su asiento automático.

Asiento de una factura de INGRESO (venta a crédito):
    Debe   Clientes ..................... total
    Debe   Retenciones a favor .......... retenciones (si el cliente nos retiene)
    Haber  Ventas (cuenta de cada línea)  subtotal
    Haber  IVA trasladado ............... IVA

Asiento de una factura de GASTO (compra a crédito):
    Debe   Gasto / activo de cada línea . subtotal
    Debe   IVA acreditable .............. IVA
    Haber  Proveedores .................. total
    Haber  Retenciones por pagar ........ retenciones (si retenemos al proveedor)
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import fila, filas, valor
from app.errores import ErrorNegocio
from app.servicios import polizas as srv_polizas

CERO = Decimal("0.00")
CENTAVO = Decimal("0.01")


def redondear(x: Decimal) -> Decimal:
    """Redondeo comercial a 2 decimales (0.005 -> 0.01), no el bancario de Python."""
    return Decimal(x).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def calcular_totales(lineas: list[dict], impuestos: list[dict]) -> dict:
    """Calcula importes por línea, impuestos sobre el subtotal y total. Función pura (fácil de probar)."""
    importes = [redondear(Decimal(l["cantidad"]) * Decimal(l["precio_unitario"])) for l in lineas]
    subtotal = sum(importes, CERO)
    detalle = []
    for imp in impuestos:
        importe = redondear(subtotal * Decimal(imp["tasa"]) / 100)
        detalle.append({**imp, "base": subtotal, "importe": importe})
    traslados = sum((d["importe"] for d in detalle if d["tipo"] == "traslado"), CERO)
    retenciones = sum((d["importe"] for d in detalle if d["tipo"] == "retencion"), CERO)
    return {"importes": importes, "subtotal": subtotal, "impuestos": detalle,
            "total_traslados": traslados, "total_retenciones": retenciones,
            "total": subtotal + traslados - retenciones}


def _empresa(conn: Connection) -> dict:
    return fila(conn, "SELECT * FROM empresa")


def crear_factura(conn: Connection, datos: dict, usuario: str) -> dict:
    tercero = fila(conn, "SELECT * FROM terceros WHERE id = :id AND activo", id=datos["tercero_id"])
    if tercero is None:
        raise ErrorNegocio("VALIDACION", "El cliente o proveedor no existe o está inactivo")
    esperado = "cliente" if datos["tipo"] == "ingreso" else "proveedor"
    if tercero["tipo"] not in (esperado, "ambos"):
        raise ErrorNegocio("VALIDACION", f"{tercero['nombre']} no está registrado como {esperado}")

    # Cuentas de las líneas: ventas -> cuentas de ingreso; compras -> gasto o activo
    permitidos = ("ingreso",) if datos["tipo"] == "ingreso" else ("gasto", "activo")
    for l in datos["lineas"]:
        c = fila(conn, "SELECT codigo, nombre, tipo, acepta_movimientos FROM cuentas WHERE id = :id", id=l["cuenta_id"])
        if c is None or c["tipo"] not in permitidos or not c["acepta_movimientos"]:
            raise ErrorNegocio("VALIDACION", f"La cuenta de la línea «{l['descripcion']}» debe ser de "
                                             f"{' o '.join(permitidos)} y aceptar movimientos")

    impuestos = []
    for codigo in datos.get("impuestos") or []:
        imp = fila(conn, "SELECT * FROM impuestos WHERE codigo = :c AND activo", c=codigo)
        if imp is None:
            raise ErrorNegocio("VALIDACION", f"El impuesto {codigo} no existe o está inactivo")
        impuestos.append(imp)

    t = calcular_totales(datos["lineas"], impuestos)
    if t["total"] <= 0:
        raise ErrorNegocio("VALIDACION", "El total de la factura debe ser mayor que cero")
    moneda, tc = srv_polizas.resolver_tipo_cambio(conn, datos.get("moneda"), datos["fecha"], datos.get("tipo_cambio"))
    vencimiento = datos.get("vencimiento") or datos["fecha"] + timedelta(days=tercero["dias_credito"])

    fid = valor(conn, """
        INSERT INTO facturas (tipo, folio, tercero_id, fecha, vencimiento, moneda, tipo_cambio, subtotal,
                              total_traslados, total_retenciones, total, notas)
        VALUES (:tipo, :folio, :ter, :f, :v, :m, :tc, :sub, :tras, :ret, :tot, :notas) RETURNING id""",
        tipo=datos["tipo"], folio=datos["folio"].strip(), ter=tercero["id"], f=datos["fecha"], v=vencimiento, m=moneda,
        tc=tc, sub=t["subtotal"], tras=t["total_traslados"], ret=t["total_retenciones"], tot=t["total"],
        notas=datos.get("notas"))
    for l, importe in zip(datos["lineas"], t["importes"]):
        conn.execute(text("""INSERT INTO factura_lineas (factura_id, descripcion, cuenta_id, cantidad, precio_unitario, importe)
                             VALUES (:f, :d, :c, :q, :p, :i)"""),
                     {"f": fid, "d": l["descripcion"], "c": l["cuenta_id"], "q": l["cantidad"],
                      "p": l["precio_unitario"], "i": importe})
    for d in t["impuestos"]:
        conn.execute(text("""INSERT INTO factura_impuestos (factura_id, impuesto_id, base, tasa, importe)
                             VALUES (:f, :i, :b, :t, :imp)"""),
                     {"f": fid, "i": d["id"], "b": d["base"], "t": d["tasa"], "imp": d["importe"]})

    poliza = srv_polizas.crear_poliza(conn, {
        "tipo": "diario", "fecha": datos["fecha"], "moneda": moneda, "tipo_cambio": tc, "contabilizar": True,
        "concepto": f"Factura de {'venta' if datos['tipo'] == 'ingreso' else 'compra'} {datos['folio']} · {tercero['nombre']}",
        "lineas": lineas_asiento_factura(conn, datos["tipo"], datos["lineas"], t, datos["folio"]),
    }, usuario, origen="factura")
    conn.execute(text("UPDATE facturas SET poliza_id = :p WHERE id = :f"), {"p": poliza["id"], "f": fid})
    return obtener(conn, fid)


def lineas_asiento_factura(conn: Connection, tipo: str, lineas: list[dict], t: dict, folio: str) -> list[dict]:
    emp = _empresa(conn)
    por_cuenta = defaultdict(lambda: CERO)
    for l, importe in zip(lineas, t["importes"]):
        por_cuenta[l["cuenta_id"]] += importe
    asiento = []
    if tipo == "ingreso":
        asiento.append({"cuenta_id": emp["cuenta_clientes_id"], "descripcion": f"Cliente · {folio}", "debe": t["total"]})
        for d in t["impuestos"]:
            if d["tipo"] == "retencion" and d["importe"] > 0:
                asiento.append({"cuenta_id": d["cuenta_ventas_id"], "descripcion": d["nombre"], "debe": d["importe"]})
        for cuenta_id, importe in por_cuenta.items():
            asiento.append({"cuenta_id": cuenta_id, "descripcion": f"Venta · {folio}", "haber": importe})
        for d in t["impuestos"]:
            if d["tipo"] == "traslado" and d["importe"] > 0:
                asiento.append({"cuenta_id": d["cuenta_ventas_id"], "descripcion": d["nombre"], "haber": d["importe"]})
    else:
        for cuenta_id, importe in por_cuenta.items():
            asiento.append({"cuenta_id": cuenta_id, "descripcion": f"Compra · {folio}", "debe": importe})
        for d in t["impuestos"]:
            if d["tipo"] == "traslado" and d["importe"] > 0:
                asiento.append({"cuenta_id": d["cuenta_compras_id"], "descripcion": d["nombre"], "debe": d["importe"]})
        asiento.append({"cuenta_id": emp["cuenta_proveedores_id"], "descripcion": f"Proveedor · {folio}", "haber": t["total"]})
        for d in t["impuestos"]:
            if d["tipo"] == "retencion" and d["importe"] > 0:
                asiento.append({"cuenta_id": d["cuenta_compras_id"], "descripcion": d["nombre"], "haber": d["importe"]})
    return asiento


def saldo_factura(conn: Connection, factura_id: int) -> Decimal:
    return Decimal(valor(conn, """SELECT f.total - coalesce((SELECT sum(monto) FROM pagos WHERE factura_id = f.id), 0)
                                   FROM facturas f WHERE f.id = :id""", id=factura_id))


def registrar_pago(conn: Connection, factura_id: int, datos: dict, usuario: str) -> dict:
    """Cobro (factura de ingreso) o pago (factura de gasto). La póliza se registra en moneda base y,
    si la factura es en moneda extranjera, la diferencia entre el tipo de cambio de la factura y el
    del día del pago se reconoce como utilidad o pérdida cambiaria."""
    f = fila(conn, "SELECT f.*, t.nombre AS tercero FROM facturas f JOIN terceros t ON t.id = f.tercero_id WHERE f.id = :id",
             id=factura_id)
    if f is None:
        raise ErrorNegocio("NO_ENCONTRADO", "La factura no existe")
    if f["estado"] == "cancelada":
        raise ErrorNegocio("VALIDACION", "La factura está cancelada")
    if datos["fecha"] < f["fecha"]:
        raise ErrorNegocio("VALIDACION", "El pago no puede ser anterior a la fecha de la factura")
    saldo = saldo_factura(conn, factura_id)
    monto = Decimal(datos["monto"])
    if monto > saldo:
        raise ErrorNegocio("VALIDACION", f"El pago ({monto:,.2f}) supera el saldo pendiente ({saldo:,.2f} {f['moneda']})")
    banco = fila(conn, "SELECT * FROM cuentas_bancarias WHERE id = :id", id=datos["cuenta_bancaria_id"])
    if banco is None:
        raise ErrorNegocio("VALIDACION", "La cuenta bancaria no existe")

    emp = _empresa(conn)
    _, tc_pago = srv_polizas.resolver_tipo_cambio(conn, f["moneda"], datos["fecha"], None)
    importe_banco = redondear(monto * tc_pago)
    importe_tercero = redondear(monto * f["tipo_cambio"])
    diferencia = importe_banco - importe_tercero
    ref = datos.get("referencia") or ""

    if f["tipo"] == "ingreso":
        lineas = [{"cuenta_id": banco["cuenta_id"], "descripcion": f"Cobro {f['folio']} {ref}".strip(), "debe": importe_banco},
                  {"cuenta_id": emp["cuenta_clientes_id"], "descripcion": f"Cliente · {f['folio']}", "haber": importe_tercero}]
        if diferencia > 0:
            lineas.append({"cuenta_id": emp["cuenta_utilidad_cambiaria_id"], "descripcion": "Utilidad cambiaria", "haber": diferencia})
        elif diferencia < 0:
            lineas.append({"cuenta_id": emp["cuenta_perdida_cambiaria_id"], "descripcion": "Pérdida cambiaria", "debe": -diferencia})
        tipo_poliza, verbo = "ingreso", "Cobro"
    else:
        lineas = [{"cuenta_id": emp["cuenta_proveedores_id"], "descripcion": f"Proveedor · {f['folio']}", "debe": importe_tercero},
                  {"cuenta_id": banco["cuenta_id"], "descripcion": f"Pago {f['folio']} {ref}".strip(), "haber": importe_banco}]
        if diferencia > 0:
            lineas.append({"cuenta_id": emp["cuenta_perdida_cambiaria_id"], "descripcion": "Pérdida cambiaria", "debe": diferencia})
        elif diferencia < 0:
            lineas.append({"cuenta_id": emp["cuenta_utilidad_cambiaria_id"], "descripcion": "Utilidad cambiaria", "haber": -diferencia})
        tipo_poliza, verbo = "egreso", "Pago"

    poliza = srv_polizas.crear_poliza(conn, {
        "tipo": tipo_poliza, "fecha": datos["fecha"], "moneda": emp["moneda_base"], "contabilizar": True,
        "concepto": f"{verbo} de factura {f['folio']} · {f['tercero']}", "lineas": lineas,
    }, usuario, origen="pago")
    pid = valor(conn, """INSERT INTO pagos (factura_id, fecha, monto, tipo_cambio, cuenta_bancaria_id, referencia, poliza_id)
                         VALUES (:f, :fe, :m, :tc, :b, :r, :p) RETURNING id""",
                f=factura_id, fe=datos["fecha"], m=monto, tc=tc_pago, b=banco["id"], r=datos.get("referencia"), p=poliza["id"])
    if saldo - monto == 0:
        conn.execute(text("UPDATE facturas SET estado = 'pagada' WHERE id = :id"), {"id": factura_id})
    return {"pago_id": pid, "poliza": poliza, "factura": obtener(conn, factura_id)}


def cancelar_factura(conn: Connection, factura_id: int, fecha: date, motivo: str, usuario: str) -> dict:
    f = fila(conn, "SELECT * FROM facturas WHERE id = :id", id=factura_id)
    if f is None:
        raise ErrorNegocio("NO_ENCONTRADO", "La factura no existe")
    if f["estado"] == "cancelada":
        raise ErrorNegocio("VALIDACION", "La factura ya está cancelada")
    if valor(conn, "SELECT count(*) FROM pagos WHERE factura_id = :id", id=factura_id):
        raise ErrorNegocio("VALIDACION", "La factura tiene pagos registrados: no se puede cancelar")
    srv_polizas.revertir(conn, f["poliza_id"], fecha, f"Cancelación de factura {f['folio']}: {motivo}", usuario)
    conn.execute(text("UPDATE facturas SET estado = 'cancelada' WHERE id = :id"), {"id": factura_id})
    return obtener(conn, factura_id)


def obtener(conn: Connection, factura_id: int) -> dict:
    f = fila(conn, """
        SELECT f.*, t.nombre AS tercero, t.rfc AS tercero_rfc,
               f.total - coalesce((SELECT sum(monto) FROM pagos WHERE factura_id = f.id), 0) AS saldo,
               p.anio || '-' || lpad(p.numero::text, 5, '0') AS folio_poliza
          FROM facturas f JOIN terceros t ON t.id = f.tercero_id LEFT JOIN polizas p ON p.id = f.poliza_id
         WHERE f.id = :id""", id=factura_id)
    if f is None:
        raise ErrorNegocio("NO_ENCONTRADO", "La factura no existe")
    f["lineas"] = filas(conn, """SELECT l.*, c.codigo AS cuenta_codigo, c.nombre AS cuenta_nombre
                                   FROM factura_lineas l JOIN cuentas c ON c.id = l.cuenta_id
                                  WHERE l.factura_id = :id ORDER BY l.id""", id=factura_id)
    f["impuestos"] = filas(conn, """SELECT fi.*, i.codigo, i.nombre, i.tipo FROM factura_impuestos fi
                                      JOIN impuestos i ON i.id = fi.impuesto_id WHERE fi.factura_id = :id""", id=factura_id)
    f["pagos"] = filas(conn, """SELECT pg.*, b.nombre AS banco, p.anio || '-' || lpad(p.numero::text, 5, '0') AS folio_poliza
                                  FROM pagos pg JOIN cuentas_bancarias b ON b.id = pg.cuenta_bancaria_id
                                  LEFT JOIN polizas p ON p.id = pg.poliza_id
                                 WHERE pg.factura_id = :id ORDER BY pg.fecha, pg.id""", id=factura_id)
    return f


def listar(conn: Connection, tipo: str | None, estado: str | None, q: str | None) -> list[dict]:
    return filas(conn, """
        SELECT f.id, f.tipo, f.folio, f.fecha, f.vencimiento, f.moneda, f.total, f.estado, t.nombre AS tercero,
               f.total - coalesce((SELECT sum(monto) FROM pagos WHERE factura_id = f.id), 0) AS saldo,
               (current_date - f.vencimiento) AS dias_vencido
          FROM facturas f JOIN terceros t ON t.id = f.tercero_id
         WHERE (CAST(:tipo AS text) IS NULL OR f.tipo = :tipo)
           AND (CAST(:estado AS text) IS NULL OR f.estado = :estado)
           AND (CAST(:q AS text) IS NULL OR f.folio ILIKE '%' || :q || '%' OR t.nombre ILIKE '%' || :q || '%')
         ORDER BY f.fecha DESC, f.id DESC""", tipo=tipo, estado=estado, q=q or None)
