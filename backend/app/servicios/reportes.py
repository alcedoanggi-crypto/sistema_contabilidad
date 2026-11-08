"""Reportes contables. Toda la aritmética la hacen las funciones de PostgreSQL (sql/003_reportes.sql);
aquí solo se arman las secciones y los totales para mostrarlos."""
from datetime import date
from decimal import Decimal

from sqlalchemy.engine import Connection

from app.db import fila, filas

CERO = Decimal("0.00")


def balanza(conn: Connection, desde: date, hasta: date, nivel: int | None = None) -> dict:
    cuentas = filas(conn, "SELECT * FROM saldos_cuentas(:d, :h)", d=desde, h=hasta)
    # Los totales se suman solo en cuentas de detalle, para no contar dos veces a las de mayor
    detalle = [c for c in cuentas if c["acepta_movimientos"]]
    totales = {
        "debe": sum((c["debe"] for c in detalle), CERO),
        "haber": sum((c["haber"] for c in detalle), CERO),
        "saldo_deudor": sum((_deudor(c) for c in detalle), CERO),
        "saldo_acreedor": sum((_acreedor(c) for c in detalle), CERO),
    }
    visibles = [c for c in cuentas if nivel is None or c["nivel"] <= nivel]
    visibles = [c for c in visibles if c["saldo_inicial"] or c["debe"] or c["haber"] or c["saldo_final"]]
    for c in visibles:
        c["saldo_deudor"], c["saldo_acreedor"] = _deudor(c), _acreedor(c)
    return {"desde": desde, "hasta": hasta, "cuentas": visibles, "totales": totales,
            "cuadra": totales["debe"] == totales["haber"] and totales["saldo_deudor"] == totales["saldo_acreedor"]}


def _saldo_deudor_neto(c: dict) -> Decimal:
    return c["saldo_final"] if c["naturaleza"] == "deudora" else -c["saldo_final"]


def _deudor(c: dict) -> Decimal:
    n = _saldo_deudor_neto(c)
    return n if n > 0 else CERO


def _acreedor(c: dict) -> Decimal:
    n = _saldo_deudor_neto(c)
    return -n if n < 0 else CERO


def estado_resultados(conn: Connection, desde: date, hasta: date) -> dict:
    cuentas = filas(conn, "SELECT * FROM estado_resultados(:d, :h) ORDER BY string_to_array(codigo, '.')::int[]",
                    d=desde, h=hasta)
    cuentas = [c for c in cuentas if c["importe"]]
    ingresos = sum((c["importe"] for c in cuentas if c["tipo"] == "ingreso" and c["acepta_movimientos"]), CERO)
    gastos = sum((c["importe"] for c in cuentas if c["tipo"] == "gasto" and c["acepta_movimientos"]), CERO)
    return {"desde": desde, "hasta": hasta,
            "ingresos": [c for c in cuentas if c["tipo"] == "ingreso"],
            "gastos": [c for c in cuentas if c["tipo"] == "gasto"],
            "total_ingresos": ingresos, "total_gastos": gastos, "utilidad": ingresos - gastos}


def balance_general(conn: Connection, corte: date) -> dict:
    filas_bg = filas(conn, "SELECT * FROM balance_general(:c)", c=corte)
    secciones = {}
    for s in ("activo", "pasivo", "capital"):
        renglones = [r for r in filas_bg if r["seccion"] == s and (r["importe"] or r["cuenta_id"] is None)]
        total = sum((r["importe"] for r in renglones if r["acepta_movimientos"]), CERO)
        secciones[s] = {"cuentas": renglones, "total": total}
    pasivo_capital = secciones["pasivo"]["total"] + secciones["capital"]["total"]
    return {"corte": corte, **secciones, "total_pasivo_capital": pasivo_capital,
            "cuadra": secciones["activo"]["total"] == pasivo_capital}


def libro_diario(conn: Connection, desde: date, hasta: date) -> dict:
    movimientos = filas(conn, """SELECT * FROM v_movimientos WHERE fecha BETWEEN :d AND :h
                                 ORDER BY fecha, folio, orden, linea_id""", d=desde, h=hasta)
    polizas, actual = [], None
    for m in movimientos:
        if actual is None or actual["poliza_id"] != m["poliza_id"]:
            actual = {k: m[k] for k in ("poliza_id", "folio", "fecha", "concepto", "estado_poliza", "tipo_poliza")}
            actual["lineas"] = []
            polizas.append(actual)
        actual["lineas"].append(m)
    return {"desde": desde, "hasta": hasta, "polizas": polizas,
            "total_debe": sum((m["debe_base"] for m in movimientos), CERO),
            "total_haber": sum((m["haber_base"] for m in movimientos), CERO)}


def libro_mayor(conn: Connection, cuenta_id: int, desde: date, hasta: date) -> dict:
    cuenta = fila(conn, "SELECT id, codigo, nombre, naturaleza, tipo FROM cuentas WHERE id = :id", id=cuenta_id)
    movimientos = filas(conn, "SELECT * FROM libro_mayor(:c, :d, :h)", c=cuenta_id, d=desde, h=hasta)
    detalle = movimientos[1:]
    return {"cuenta": cuenta, "desde": desde, "hasta": hasta,
            "saldo_inicial": movimientos[0]["saldo"] if movimientos else CERO,
            "movimientos": detalle,
            "total_debe": sum((m["debe"] for m in detalle), CERO),
            "total_haber": sum((m["haber"] for m in detalle), CERO),
            "saldo_final": detalle[-1]["saldo"] if detalle else (movimientos[0]["saldo"] if movimientos else CERO)}


def antiguedad(conn: Connection, tipo: str, corte: date) -> dict:
    renglones = filas(conn, "SELECT * FROM antiguedad_saldos(:t, :c)", t=tipo, c=corte)
    columnas = ("por_vencer", "d0_30", "d31_60", "d61_90", "mas_90", "total")
    for r in renglones:
        for k in columnas:
            r[k] = r[k] or CERO
    totales = {k: sum((r[k] for r in renglones), CERO) for k in columnas}
    detalle = filas(conn, """SELECT * FROM saldos_facturas(:c) WHERE tipo = :t ORDER BY dias_vencido DESC""",
                    c=corte, t="ingreso" if tipo == "cxc" else "gasto")
    return {"tipo": tipo, "corte": corte, "terceros": renglones, "totales": totales, "facturas": detalle}
