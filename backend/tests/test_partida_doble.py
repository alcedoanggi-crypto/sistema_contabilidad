"""La regla de oro: debe = haber. Se prueba en las tres capas (servicio, base de datos y API)."""
from datetime import date
from decimal import Decimal as D

import pytest
from sqlalchemy import text

from app.errores import ErrorNegocio
from app.servicios.polizas import validar_partida_doble

from .conftest import falla_con

F = date(2026, 6, 10)


# --- capa 1: validación en Python (mensaje inmediato al usuario) ---------------------------
def test_poliza_cuadrada_pasa():
    assert validar_partida_doble([{"debe": D("100.10")}, {"haber": D("60.05")}, {"haber": D("40.05")}]) == (D("100.10"), D("100.10"))


@pytest.mark.parametrize("lineas, mensaje", [
    ([{"debe": D("100.00")}, {"haber": D("99.99")}], "diferencia 0.01"),
    ([{"debe": D("50")}], "al menos dos líneas"),
    ([{"debe": D("10"), "haber": D("10")}, {"haber": D("10")}], "solo uno"),
    ([{"debe": D("0")}, {"haber": D("0")}], "solo uno"),
    ([{"debe": D("-5")}, {"haber": D("-5")}], "negativos"),
])
def test_polizas_invalidas_se_rechazan(lineas, mensaje):
    with pytest.raises(ErrorNegocio) as e:
        validar_partida_doble(lineas)
    assert mensaje in e.value.mensaje


def test_centavos_no_se_pierden_con_decimal():
    # Con float, 0.1 + 0.2 da 0.30000000000000004: con Decimal (NUMERIC) da exactamente 0.30
    assert 0.1 + 0.2 != 0.3
    assert D("0.1") + D("0.2") == D("0.3")
    validar_partida_doble([{"debe": D("0.10")}] * 10 + [{"haber": D("1.00")}])


# --- capa 2: la base de datos es la garantía final ------------------------------------------
def test_la_base_rechaza_contabilizar_una_poliza_descuadrada(conn, poliza):
    p = poliza(F, [("1.1.01", "100.00", 0), ("4.1.01", 0, "100.00")], contabilizar=False)
    conn.execute(text("UPDATE poliza_lineas SET haber = 99.00 WHERE poliza_id = :p AND haber > 0"), {"p": p["id"]})
    with falla_con(conn, "DESCUADRE"):
        conn.execute(text("SELECT contabilizar_poliza(:p)"), {"p": p["id"]})


def test_una_linea_no_puede_tener_debe_y_haber(conn, poliza, cta):
    p = poliza(F, [("1.1.01", 10, 0), ("4.1.01", 0, 10)], contabilizar=False)
    with falla_con(conn, "check"):
        conn.execute(text("INSERT INTO poliza_lineas (poliza_id, cuenta_id, debe, haber) VALUES (:p, :c, 5, 5)"),
                     {"p": p["id"], "c": cta("1.1.01")})


def test_cuenta_de_mayor_no_acepta_movimientos(conn, poliza):
    with falla_con(conn, "es de mayor"):
        poliza(F, [("1.1", 10, 0), ("4.1.01", 0, 10)])


def test_contabilizar_asigna_folio_consecutivo(poliza):
    a = poliza(F, [("1.1.01", 10, 0), ("4.1.01", 0, 10)])
    b = poliza(F, [("1.1.01", 20, 0), ("4.1.01", 0, 20)])
    assert a["estado"] == "contabilizada" and b["numero"] == a["numero"] + 1


def test_redondeo_en_moneda_extranjera_queda_cuadrado_en_moneda_base(conn, poliza):
    # 3 líneas de 33.33 EUR a 1.10 generan centavos de redondeo: la base los ajusta
    p = poliza(F, [("1.1.01", "99.99", 0), ("4.1.01", 0, "33.33"), ("4.1.01", 0, "33.33"), ("4.1.01", 0, "33.33")],
               moneda="EUR", tipo_cambio=D("1.105"))
    debe = sum(l["debe_base"] for l in p["lineas"])
    haber = sum(l["haber_base"] for l in p["lineas"])
    assert debe == haber == D("110.49")


# --- capa 3: la API responde 422 con un mensaje claro ---------------------------------------
def test_api_rechaza_poliza_descuadrada(cliente, cta):
    r = cliente.post("/api/polizas", json={
        "fecha": "2026-06-10", "concepto": "Descuadrada", "contabilizar": True,
        "lineas": [{"cuenta_id": cta("1.1.01"), "debe": "100.00"}, {"cuenta_id": cta("4.1.01"), "haber": "90.00"}]})
    assert r.status_code == 422
    assert r.json()["codigo"] == "DESCUADRE"
    assert "diferencia 10.00" in r.json()["detail"]


def test_api_rechaza_mas_de_dos_decimales(cliente, cta):
    r = cliente.post("/api/polizas", json={
        "fecha": "2026-06-10", "concepto": "x", "lineas": [{"cuenta_id": cta("1.1.01"), "debe": "1.005"},
                                                           {"cuenta_id": cta("4.1.01"), "haber": "1.005"}]})
    assert r.status_code == 422


def test_api_guarda_borrador_descuadrado_pero_no_lo_contabiliza(cliente, cta):
    r = cliente.post("/api/polizas", json={
        "fecha": "2026-06-10", "concepto": "Borrador", "contabilizar": False,
        "lineas": [{"cuenta_id": cta("1.1.01"), "debe": "100.00"}, {"cuenta_id": cta("4.1.01"), "haber": "1.00"}]})
    assert r.status_code == 201 and r.json()["estado"] == "borrador"
    r2 = cliente.post(f"/api/polizas/{r.json()['id']}/contabilizar")
    assert r2.status_code == 422
