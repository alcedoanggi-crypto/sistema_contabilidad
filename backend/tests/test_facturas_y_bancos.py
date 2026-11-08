"""Facturas con impuestos, pagos multimoneda y conciliación bancaria."""
from datetime import date
from decimal import Decimal as D

from sqlalchemy import text

from app.servicios import conciliacion, facturas

from .conftest import falla_con

IVA = {"tipo": "traslado", "tasa": D("16")}
RET_ISR = {"tipo": "retencion", "tasa": D("10")}
RET_IVA = {"tipo": "retencion", "tasa": D("10.6667")}


def test_calculo_de_impuestos_con_retenciones():
    t = facturas.calcular_totales([{"cantidad": D("1"), "precio_unitario": D("1800")}], [IVA, RET_ISR, RET_IVA])
    assert t["subtotal"] == D("1800.00")
    assert t["total_traslados"] == D("288.00")
    assert t["total_retenciones"] == D("180.00") + D("192.00")
    assert t["total"] == D("1716.00")


def test_redondeo_comercial_medio_centavo_hacia_arriba():
    t = facturas.calcular_totales([{"cantidad": D("3"), "precio_unitario": D("0.335")}], [])
    assert t["subtotal"] == D("1.01")          # 1.005 -> 1.01 (el redondeo bancario daría 1.00)


def _tercero(conn, tipo="cliente"):
    return conn.execute(text("INSERT INTO terceros (tipo, nombre, dias_credito) VALUES (:t, 'Tercero Prueba', 30) RETURNING id"),
                        {"t": tipo}).scalar()


def test_factura_de_venta_genera_su_asiento(conn, cta):
    f = facturas.crear_factura(conn, {"tipo": "ingreso", "folio": "V-1", "tercero_id": _tercero(conn), "fecha": date(2026, 6, 1),
                                      "impuestos": ["IVA16", "RET_ISR10"],
                                      "lineas": [{"descripcion": "Servicio", "cuenta_id": cta("4.1.01"), "cantidad": D("2"),
                                                  "precio_unitario": D("500")}]}, "pruebas")
    assert f["total"] == D("1060.00") and f["vencimiento"] == date(2026, 7, 1)
    lineas = conn.execute(text("""SELECT c.codigo, l.debe, l.haber FROM poliza_lineas l JOIN cuentas c ON c.id = l.cuenta_id
                                   WHERE l.poliza_id = :p ORDER BY l.orden"""), {"p": f["poliza_id"]}).all()
    assert [tuple(x) for x in lineas] == [("1.1.03", D("1060.00"), D("0")), ("1.1.05", D("100.00"), D("0")),
                                          ("4.1.01", D("0"), D("1000.00")), ("2.1.03", D("0"), D("160.00"))]


def test_factura_de_compra_con_retenciones_genera_su_asiento(conn, cta):
    f = facturas.crear_factura(conn, {"tipo": "gasto", "folio": "R-1", "tercero_id": _tercero(conn, "proveedor"),
                                      "fecha": date(2026, 6, 1), "impuestos": ["IVA16", "RET_ISR10", "RET_IVA"],
                                      "lineas": [{"descripcion": "Renta", "cuenta_id": cta("5.1.02"), "cantidad": D("1"),
                                                  "precio_unitario": D("1800")}]}, "pruebas")
    totales = conn.execute(text("SELECT sum(debe), sum(haber) FROM poliza_lineas WHERE poliza_id = :p"), {"p": f["poliza_id"]}).one()
    assert totales[0] == totales[1] == D("2088.00")


def test_pago_en_euros_registra_diferencia_cambiaria(conn, cta, banco_id):
    # factura a 1.10 (enero); cobro con tipo de cambio 1.20 (marzo) -> utilidad cambiaria de 0.10 por euro
    f = facturas.crear_factura(conn, {"tipo": "ingreso", "folio": "E-1", "tercero_id": _tercero(conn), "fecha": date(2026, 2, 1),
                                      "moneda": "EUR", "impuestos": ["IVA0"],
                                      "lineas": [{"descripcion": "Exportación", "cuenta_id": cta("4.1.02"), "cantidad": D("1"),
                                                  "precio_unitario": D("1000")}]}, "pruebas")
    r = facturas.registrar_pago(conn, f["id"], {"fecha": date(2026, 3, 5), "monto": D("1000"), "cuenta_bancaria_id": banco_id}, "pruebas")
    lineas = {l["cuenta_codigo"]: l for l in r["poliza"]["lineas"]}
    assert lineas["1.1.02.01"]["debe"] == D("1200.00")
    assert lineas["1.1.03"]["haber"] == D("1100.00")
    assert lineas["4.2.01"]["haber"] == D("100.00")
    assert r["factura"]["estado"] == "pagada"


def test_no_se_paga_mas_que_el_saldo_ni_se_cancela_con_pagos(conn, cta, banco_id):
    f = facturas.crear_factura(conn, {"tipo": "ingreso", "folio": "V-2", "tercero_id": _tercero(conn), "fecha": date(2026, 6, 1),
                                      "lineas": [{"descripcion": "x", "cuenta_id": cta("4.1.01"), "cantidad": D("1"),
                                                  "precio_unitario": D("100")}]}, "pruebas")
    with falla_con(conn, "supera el saldo"):
        facturas.registrar_pago(conn, f["id"], {"fecha": date(2026, 6, 2), "monto": D("100.01"), "cuenta_bancaria_id": banco_id}, "pruebas")
    facturas.registrar_pago(conn, f["id"], {"fecha": date(2026, 6, 2), "monto": D("40"), "cuenta_bancaria_id": banco_id}, "pruebas")
    assert facturas.saldo_factura(conn, f["id"]) == D("60.00")
    with falla_con(conn, "tiene pagos"):
        facturas.cancelar_factura(conn, f["id"], date(2026, 6, 3), "no", "pruebas")


def test_cancelar_factura_revierte_su_poliza(conn, cta):
    f = facturas.crear_factura(conn, {"tipo": "ingreso", "folio": "V-3", "tercero_id": _tercero(conn), "fecha": date(2026, 6, 1),
                                      "impuestos": ["IVA16"], "lineas": [{"descripcion": "x", "cuenta_id": cta("4.1.01"),
                                                                          "cantidad": D("1"), "precio_unitario": D("100")}]}, "pruebas")
    facturas.cancelar_factura(conn, f["id"], date(2026, 6, 2), "error", "pruebas")
    saldo = conn.execute(text("SELECT saldo_final FROM saldos_cuentas('2026-01-01','2026-12-31') WHERE codigo = '1.1.03'")).scalar()
    assert saldo == D("0.00")


# --- conciliación bancaria ---------------------------------------------------------------------
def test_lectura_de_csv_con_distintos_formatos():
    csv = ("Fecha;Concepto;Ref;Deposito;Retiro\n"
           "05/06/2026;Cobro cliente;TRF-1;1.234,50;\n"
           "06/06/2026;Comisión;;;12,50\n").encode()
    movs = conciliacion.leer_csv(csv)
    assert [(m["fecha"], m["monto"]) for m in movs] == [(date(2026, 6, 5), D("1234.50")), (date(2026, 6, 6), D("-12.50"))]


def test_importar_no_duplica_y_concilia_por_referencia_y_fecha(conn, poliza, banco_id):
    poliza(date(2026, 6, 1), [("1.1.02.01", "500.00", 0), ("4.1.01", 0, "500.00")], concepto="Cobro TRF-777")
    poliza(date(2026, 6, 3), [("5.1.02", "80.00", 0), ("1.1.02.01", 0, "80.00")], concepto="Pago servicio")
    csv = ("fecha,descripcion,referencia,monto\n"
           "2026-06-02,DEPOSITO,TRF-777,500.00\n"
           "2026-06-04,CARGO SERVICIO,,-80.00\n"
           "2026-06-05,COMISION,COM,-9.99\n").encode()
    primera = conciliacion.importar(conn, banco_id, "junio.csv", csv)
    segunda = conciliacion.importar(conn, banco_id, "junio.csv", csv)
    assert primera["nuevas"] == 3 and segunda["nuevas"] == 0 and segunda["duplicadas"] == 3

    r = conciliacion.conciliar_automatico(conn, banco_id)
    criterios = sorted(d["criterio"] for d in r["detalle"])
    assert criterios == ["importe y fecha", "importe y referencia"]
    rep = conciliacion.reporte(conn, banco_id, date(2026, 6, 30))
    assert [m["descripcion"] for m in rep["solo_banco"]] == ["COMISION"]   # la comisión aún no está en libros
    assert rep["cuadra"]


def test_no_empareja_cuando_hay_empate(conn, poliza, banco_id):
    poliza(date(2026, 6, 1), [("1.1.02.01", "50.00", 0), ("4.1.01", 0, "50.00")])
    poliza(date(2026, 6, 3), [("1.1.02.01", "50.00", 0), ("4.1.01", 0, "50.00")])
    conciliacion.importar(conn, banco_id, "x.csv", b"fecha,descripcion,monto\n2026-06-02,DEPOSITO,50.00\n")
    assert conciliacion.conciliar_automatico(conn, banco_id)["emparejados"] == 0
