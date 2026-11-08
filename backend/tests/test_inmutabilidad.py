"""Inmutabilidad contable y cierre de periodos: lo hace cumplir PostgreSQL aunque se use SQL directo."""
from datetime import date
from decimal import Decimal as D

from sqlalchemy import text

from app.servicios import polizas

from .conftest import falla_con


def test_no_se_edita_una_poliza_contabilizada(conn, poliza):
    p = poliza(date(2026, 6, 1), [("1.1.01", 100, 0), ("4.1.01", 0, 100)])
    with falla_con(conn, "INMUTABLE"):
        conn.execute(text("UPDATE poliza_lineas SET debe = 1 WHERE poliza_id = :p AND debe > 0"), {"p": p["id"]})
    with falla_con(conn, "INMUTABLE"):
        conn.execute(text("UPDATE polizas SET concepto = 'cambiado' WHERE id = :p"), {"p": p["id"]})


def test_no_se_borra_una_poliza_contabilizada(conn, poliza):
    p = poliza(date(2026, 6, 1), [("1.1.01", 100, 0), ("4.1.01", 0, 100)])
    with falla_con(conn, "INMUTABLE"):
        conn.execute(text("DELETE FROM polizas WHERE id = :p"), {"p": p["id"]})
    with falla_con(conn, "INMUTABLE"):
        conn.execute(text("DELETE FROM poliza_lineas WHERE poliza_id = :p"), {"p": p["id"]})


def test_no_se_puede_marcar_cancelada_sin_reversa(conn, poliza):
    p = poliza(date(2026, 6, 1), [("1.1.01", 100, 0), ("4.1.01", 0, 100)])
    with falla_con(conn, "INMUTABLE"):
        conn.execute(text("UPDATE polizas SET estado = 'cancelada' WHERE id = :p"), {"p": p["id"]})


def test_un_borrador_si_se_edita_y_se_borra(conn, poliza):
    p = poliza(date(2026, 6, 1), [("1.1.01", 100, 0), ("4.1.01", 0, 100)], contabilizar=False)
    conn.execute(text("UPDATE poliza_lineas SET debe = 50 WHERE poliza_id = :p AND debe > 0"), {"p": p["id"]})
    conn.execute(text("DELETE FROM polizas WHERE id = :p"), {"p": p["id"]})
    assert conn.execute(text("SELECT count(*) FROM poliza_lineas WHERE poliza_id = :p"), {"p": p["id"]}).scalar() == 0


def test_la_reversa_es_espejo_y_deja_saldos_en_cero(conn, poliza, cta):
    p = poliza(date(2026, 6, 1), [("1.1.01", "250.75", 0), ("4.1.01", 0, "250.75")])
    r = polizas.revertir(conn, p["id"], date(2026, 6, 2), "Error de captura", "pruebas")
    assert r["origen"] == "reversa" and r["reversa_de"] == p["id"]
    assert [(l["cuenta_id"], l["debe"], l["haber"]) for l in r["lineas"]] == \
           [(l["cuenta_id"], l["haber"], l["debe"]) for l in p["lineas"]]
    original = polizas.obtener(conn, p["id"])
    assert original["estado"] == "cancelada" and original["cancelada_por"] == r["id"]
    saldo = conn.execute(text("SELECT saldo_final FROM saldos_cuentas('2026-01-01', '2026-12-31') WHERE codigo = '1.1.01'")).scalar()
    assert saldo == D("0.00")


def test_no_se_revierte_dos_veces(conn, poliza):
    p = poliza(date(2026, 6, 1), [("1.1.01", 10, 0), ("4.1.01", 0, 10)])
    polizas.revertir(conn, p["id"], date(2026, 6, 1), "uno", "pruebas")
    with falla_con(conn, "solo se revierte una póliza contabilizada"):
        polizas.revertir(conn, p["id"], date(2026, 6, 1), "dos", "pruebas")


def test_periodo_cerrado_bloquea_altas_cambios_y_reversas(conn, poliza):
    p = poliza(date(2026, 5, 20), [("1.1.01", 10, 0), ("4.1.01", 0, 10)])
    conn.execute(text("SELECT cerrar_periodo(2026, 5, 'pruebas')"))
    with falla_con(conn, "PERIODO_CERRADO"):
        poliza(date(2026, 5, 25), [("1.1.01", 5, 0), ("4.1.01", 0, 5)])
    with falla_con(conn, "PERIODO_CERRADO"):
        polizas.revertir(conn, p["id"], date(2026, 5, 31), "no debería", "pruebas")
    # la reversa con fecha de un mes abierto sí procede: así se corrige un mes cerrado
    r = polizas.revertir(conn, p["id"], date(2026, 6, 1), "corrección en junio", "pruebas")
    assert r["estado"] == "contabilizada"


def test_no_se_cierra_un_mes_con_borradores(conn, poliza):
    poliza(date(2026, 4, 3), [("1.1.01", 10, 0), ("4.1.01", 0, 10)], contabilizar=False)
    with falla_con(conn, "borrador"):
        conn.execute(text("SELECT cerrar_periodo(2026, 4, 'pruebas')"))


def test_reabrir_requiere_motivo_y_queda_en_bitacora(conn):
    conn.execute(text("SELECT cerrar_periodo(2026, 3, 'pruebas')"))
    with falla_con(conn, "motivo"):
        conn.execute(text("SELECT reabrir_periodo(2026, 3, 'pruebas', '')"))
    conn.execute(text("SELECT reabrir_periodo(2026, 3, 'pruebas', 'ajuste de auditoría')"))
    assert conn.execute(text("SELECT count(*) FROM bitacora WHERE accion IN ('cerrar', 'reabrir')")).scalar() >= 2


def test_api_contador_no_puede_reabrir_y_consulta_no_puede_capturar(cliente, cta):
    from app.seguridad import crear_token
    cliente.headers["Authorization"] = f"Bearer {crear_token({'usuario': 'consulta', 'rol': 'consulta'})}"
    r = cliente.post("/api/polizas", json={"fecha": "2026-06-10", "concepto": "x", "lineas": [
        {"cuenta_id": cta("1.1.01"), "debe": "1"}, {"cuenta_id": cta("4.1.01"), "haber": "1"}]})
    assert r.status_code == 403
    cliente.headers["Authorization"] = f"Bearer {crear_token({'usuario': 'contador', 'rol': 'contador'})}"
    assert cliente.post("/api/periodos/2026/1/reabrir", json={"motivo": "prueba"}).status_code == 403
