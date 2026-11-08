"""Cálculo de reportes con un escenario de cifras conocidas (se puede verificar a mano).

Escenario 2026 (USD):
  01/02  Aportación de capital ........ Bancos 10,000 / Capital 10,000
  05/02  Venta de contado ............. Bancos  1,160 / Ventas 1,000 + IVA 160
  10/02  Renta pagada ................. Renta 500 / Bancos 500
  28/02  Depreciación ................. Depreciación 100 / Dep. acumulada 100
  Un borrador de 999 (no debe contar en ningún reporte)
"""
from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.servicios import reportes

BANCO = "1.1.02.01"


@pytest.fixture
def escenario(poliza):
    poliza(date(2026, 2, 1), [(BANCO, 10000, 0), ("3.1", 0, 10000)])
    poliza(date(2026, 2, 5), [(BANCO, 1160, 0), ("4.1.01", 0, 1000), ("2.1.03", 0, 160)])
    poliza(date(2026, 2, 10), [("5.1.02", 500, 0), (BANCO, 0, 500)])
    poliza(date(2026, 2, 28), [("5.1.06", 100, 0), ("1.2.03", 0, 100)])
    poliza(date(2026, 2, 15), [("5.1.07", 999, 0), (BANCO, 0, 999)], contabilizar=False)


def test_balanza_cuadra_y_suma_lo_esperado(conn, escenario):
    b = reportes.balanza(conn, date(2026, 1, 1), date(2026, 2, 28))
    assert b["cuadra"]
    assert b["totales"]["debe"] == b["totales"]["haber"] == D("11760.00")
    # saldos deudores = acreedores (la balanza de saldos también cuadra)
    assert b["totales"]["saldo_deudor"] == b["totales"]["saldo_acreedor"] == D("11260.00")


def test_cuentas_de_mayor_suman_sus_subcuentas(conn, escenario):
    saldos = {c["codigo"]: c for c in reportes.balanza(conn, date(2026, 1, 1), date(2026, 2, 28))["cuentas"]}
    assert saldos[BANCO]["saldo_final"] == D("10660.00")
    assert saldos["1.1.02"]["saldo_final"] == saldos["1.1"]["saldo_final"] == D("10660.00")


def test_el_borrador_no_afecta_ningun_saldo(conn, escenario):
    saldos = {c["codigo"]: c for c in reportes.balanza(conn, date(2026, 1, 1), date(2026, 2, 28))["cuentas"]}
    assert "5.1.07" not in saldos


def test_estado_de_resultados(conn, escenario):
    er = reportes.estado_resultados(conn, date(2026, 1, 1), date(2026, 2, 28))
    assert er["total_ingresos"] == D("1000.00")
    assert er["total_gastos"] == D("600.00")
    assert er["utilidad"] == D("400.00")


def test_balance_general_cuadra_con_cuenta_complementaria(conn, escenario):
    bg = reportes.balance_general(conn, date(2026, 2, 28))
    assert bg["cuadra"]
    # Activo = bancos 10,660 - depreciación acumulada 100 (resta aunque sea de naturaleza acreedora)
    assert bg["activo"]["total"] == D("10560.00")
    assert bg["pasivo"]["total"] == D("160.00")
    # Capital = 10,000 aportado + 400 de utilidad del ejercicio
    assert bg["capital"]["total"] == D("10400.00")


def test_libro_mayor_con_saldo_acumulado(conn, escenario, cta):
    m = reportes.libro_mayor(conn, cta(BANCO), date(2026, 2, 3), date(2026, 2, 28))
    assert m["saldo_inicial"] == D("10000.00")
    assert [x["saldo"] for x in m["movimientos"]] == [D("11160.00"), D("10660.00")]
    assert m["saldo_final"] == D("10660.00")


def test_resultados_empiezan_en_cero_cada_anio(conn, escenario, poliza):
    poliza(date(2027, 1, 15), [(BANCO, 50, 0), ("4.1.01", 0, 50)])
    er = reportes.estado_resultados(conn, date(2027, 1, 1), date(2027, 1, 31))
    assert er["utilidad"] == D("50.00")                      # no arrastra los 400 de 2026
    bg = reportes.balance_general(conn, date(2027, 1, 31))
    assert bg["cuadra"]
    anteriores = next(c for c in bg["capital"]["cuentas"] if c["nombre"] == "Resultados de ejercicios anteriores")
    assert anteriores["importe"] == D("400.00")              # pasan al capital como resultados anteriores


def test_libro_diario_solo_incluye_contabilizadas(conn, escenario):
    d = reportes.libro_diario(conn, date(2026, 2, 1), date(2026, 2, 28))
    assert len(d["polizas"]) == 4 and d["total_debe"] == d["total_haber"] == D("11760.00")


def test_antiguedad_de_saldos_por_rangos(conn, cliente, cta):
    tercero = conn.execute(text("INSERT INTO terceros (tipo, nombre, dias_credito) VALUES ('cliente', 'Cliente Prueba', 0) RETURNING id")).scalar()
    for folio, fecha_f, vence in (("F1", "2026-06-25", "2026-06-25"), ("F2", "2026-05-20", "2026-05-20"),
                                  ("F3", "2026-04-15", "2026-04-15"), ("F4", "2026-02-01", "2026-02-01"),
                                  ("F5", "2026-07-01", "2026-07-20")):
        r = cliente.post("/api/facturas", json={"tipo": "ingreso", "folio": folio, "tercero_id": tercero, "fecha": fecha_f,
                                                "vencimiento": vence, "lineas": [{"descripcion": "x", "cuenta_id": cta("4.1.01"),
                                                                                    "cantidad": "1", "precio_unitario": "100"}]})
        assert r.status_code == 201, r.text
    a = reportes.antiguedad(conn, "cxc", date(2026, 7, 4))
    t = a["totales"]
    # F5 aún no vence; F1 tiene 9 días; F2 45; F3 80; F4 153
    assert (t["por_vencer"], t["d0_30"], t["d31_60"], t["d61_90"], t["mas_90"]) == \
           (D("100.00"), D("100.00"), D("100.00"), D("100.00"), D("100.00"))
    assert t["total"] == D("500.00")
