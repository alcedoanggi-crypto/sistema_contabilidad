"""Libros y estados financieros, en JSON o exportados a PDF / Excel (?formato=pdf|xlsx)."""
from datetime import date

from fastapi import APIRouter, Depends, Response
from sqlalchemy.engine import Connection

from app.db import get_conn, valor
from app.seguridad import puede_leer
from app.servicios import exportar, reportes as srv

router = APIRouter(prefix="/reportes")


def _rango(desde: date, hasta: date) -> str:
    return f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"


def _salida(conn, formato: str | None, datos: dict, nombre: str, titulo: str, subtitulo: str, columnas, renglones,
            totales=None, numericas=frozenset(), horizontal=False, negritas=frozenset()):
    if formato not in ("pdf", "xlsx"):
        return datos
    empresa = valor(conn, "SELECT nombre FROM empresa") + f"  ·  Cifras en {valor(conn, 'SELECT moneda_base FROM empresa')}"
    if formato == "pdf":
        contenido = exportar.a_pdf(titulo, subtitulo, empresa, columnas, renglones, totales, set(numericas), horizontal, set(negritas))
        tipo = "application/pdf"
    else:
        contenido = exportar.a_excel(titulo, subtitulo, empresa, columnas, renglones, totales, set(numericas), set(negritas))
        tipo = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(contenido, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.{formato}"'})


def _sangria(c: dict) -> str:
    return "    " * (c["nivel"] - 1) + c["nombre"]


@router.get("/balanza")
def balanza(desde: date, hasta: date, nivel: int | None = None, formato: str | None = None,
            conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    d = srv.balanza(conn, desde, hasta, nivel)
    renglones = [[c["codigo"], _sangria(c), c["saldo_inicial"], c["debe"], c["haber"], c["saldo_deudor"], c["saldo_acreedor"]]
                 for c in d["cuentas"]]
    t = d["totales"]
    return _salida(conn, formato, d, f"balanza_{desde}_{hasta}", "Balanza de comprobación", _rango(desde, hasta),
                   ["Código", "Cuenta", "Saldo inicial", "Debe", "Haber", "Saldo deudor", "Saldo acreedor"], renglones,
                   ["", "Totales (cuentas de detalle)", "", t["debe"], t["haber"], t["saldo_deudor"], t["saldo_acreedor"]],
                   numericas={2, 3, 4, 5, 6}, horizontal=True,
                   negritas={i for i, c in enumerate(d["cuentas"]) if not c["acepta_movimientos"]})


@router.get("/estado-resultados")
def estado_resultados(desde: date, hasta: date, formato: str | None = None,
                      conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    d = srv.estado_resultados(conn, desde, hasta)
    renglones, negritas = [["", "INGRESOS", None]], {0}
    renglones += [[c["codigo"], _sangria(c), c["importe"]] for c in d["ingresos"]]
    renglones.append(["", "Total ingresos", d["total_ingresos"]])
    negritas.add(len(renglones) - 1)
    renglones.append(["", "GASTOS", None])
    negritas.add(len(renglones) - 1)
    renglones += [[c["codigo"], _sangria(c), c["importe"]] for c in d["gastos"]]
    renglones.append(["", "Total gastos", d["total_gastos"]])
    negritas.add(len(renglones) - 1)
    return _salida(conn, formato, d, f"estado_resultados_{desde}_{hasta}", "Estado de resultados", _rango(desde, hasta),
                   ["Código", "Cuenta", "Importe"], renglones,
                   ["", "UTILIDAD (PÉRDIDA) DEL PERIODO", d["utilidad"]], numericas={2}, negritas=negritas)


@router.get("/balance-general")
def balance_general(corte: date, formato: str | None = None, conn: Connection = Depends(get_conn),
                    _: dict = Depends(puede_leer)):
    d = srv.balance_general(conn, corte)
    renglones, negritas = [], set()
    for clave, titulo in (("activo", "ACTIVO"), ("pasivo", "PASIVO"), ("capital", "CAPITAL CONTABLE")):
        renglones.append(["", titulo, None])
        negritas.add(len(renglones) - 1)
        renglones += [[c["codigo"] or "", "    " * ((c["nivel"] or 2) - 1) + c["nombre"], c["importe"]] for c in d[clave]["cuentas"]]
        renglones.append(["", f"Total {titulo.lower()}", d[clave]["total"]])
        negritas.add(len(renglones) - 1)
    return _salida(conn, formato, d, f"balance_general_{corte}", "Balance general", f"Al {corte:%d/%m/%Y}",
                   ["Código", "Cuenta", "Importe"], renglones,
                   ["", "TOTAL PASIVO + CAPITAL", d["total_pasivo_capital"]], numericas={2}, negritas=negritas)


@router.get("/libro-diario")
def libro_diario(desde: date, hasta: date, formato: str | None = None, conn: Connection = Depends(get_conn),
                 _: dict = Depends(puede_leer)):
    d = srv.libro_diario(conn, desde, hasta)
    renglones, negritas = [], set()
    for p in d["polizas"]:
        estado = " (cancelada)" if p["estado_poliza"] == "cancelada" else ""
        renglones.append([p["fecha"], p["folio"], p["concepto"] + estado, None, None])
        negritas.add(len(renglones) - 1)
        renglones += [["", l["cuenta_codigo"], "    " + l["cuenta_nombre"] + (f" — {l['descripcion']}" if l["descripcion"] else ""),
                       l["debe_base"] or None, l["haber_base"] or None] for l in p["lineas"]]
    return _salida(conn, formato, d, f"libro_diario_{desde}_{hasta}", "Libro diario", _rango(desde, hasta),
                   ["Fecha", "Póliza / Cuenta", "Concepto", "Debe", "Haber"], renglones,
                   ["", "", "Totales", d["total_debe"], d["total_haber"]], numericas={3, 4}, negritas=negritas)


@router.get("/libro-mayor")
def libro_mayor(cuenta_id: int, desde: date, hasta: date, formato: str | None = None,
                conn: Connection = Depends(get_conn), _: dict = Depends(puede_leer)):
    d = srv.libro_mayor(conn, cuenta_id, desde, hasta)
    renglones = [["", "", "Saldo inicial", None, None, d["saldo_inicial"]]]
    renglones += [[m["fecha"], m["folio"], m["concepto"], m["debe"], m["haber"], m["saldo"]] for m in d["movimientos"]]
    c = d["cuenta"]
    return _salida(conn, formato, d, f"mayor_{c['codigo']}_{desde}_{hasta}", f"Libro mayor · {c['codigo']} {c['nombre']}",
                   _rango(desde, hasta), ["Fecha", "Póliza", "Concepto", "Debe", "Haber", "Saldo"], renglones,
                   ["", "", "Totales y saldo final", d["total_debe"], d["total_haber"], d["saldo_final"]],
                   numericas={3, 4, 5}, negritas={0})


@router.get("/antiguedad")
def antiguedad(tipo: str, corte: date, formato: str | None = None, conn: Connection = Depends(get_conn),
               _: dict = Depends(puede_leer)):
    d = srv.antiguedad(conn, tipo, corte)
    claves = ("por_vencer", "d0_30", "d31_60", "d61_90", "mas_90", "total")
    renglones = [[r["tercero"]] + [r[k] for k in claves] for r in d["terceros"]]
    titulo = "Antigüedad de cuentas por cobrar" if tipo == "cxc" else "Antigüedad de cuentas por pagar"
    return _salida(conn, formato, d, f"antiguedad_{tipo}_{corte}", titulo, f"Al {corte:%d/%m/%Y} · días vencidos",
                   ["Cliente / proveedor", "Por vencer", "1-30", "31-60", "61-90", "Más de 90", "Total"], renglones,
                   ["Totales"] + [d["totales"][k] for k in claves], numericas={1, 2, 3, 4, 5, 6}, horizontal=True)
