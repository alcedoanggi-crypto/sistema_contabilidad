"""Conciliación bancaria: importar el estado de cuenta (CSV) y emparejarlo con los libros.

Algoritmo de emparejamiento automático (uno a uno, nunca adivina):
  1. Mismo importe y la referencia del banco aparece en la póliza  -> se empareja.
  2. Mismo importe y fecha dentro de la tolerancia (± días)          -> se empareja con
     el movimiento de libros de fecha más cercana, solo si no hay empate.
Lo que no cumple queda pendiente para revisarlo a mano.
"""
import csv
import hashlib
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import fila, filas, valor
from app.errores import ErrorNegocio
from app.servicios import polizas as srv_polizas

CERO = Decimal("0.00")
ALIAS = {
    "fecha": ("fecha", "date", "fecha operacion", "fecha_operacion"),
    "descripcion": ("descripcion", "descripción", "concepto", "detalle"),
    "referencia": ("referencia", "ref", "folio", "numero"),
    "monto": ("monto", "importe", "amount"),
    "deposito": ("deposito", "depósito", "abono", "abonos", "credito"),
    "retiro": ("retiro", "cargo", "cargos", "debito"),
}


def _fecha(texto: str) -> date:
    texto = texto.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"fecha no reconocida «{texto}»")


def _monto(texto: str) -> Decimal:
    t = (texto or "").strip().replace("$", "").replace(" ", "")
    if not t:
        return CERO
    if "," in t and "." in t:                       # 1,234.56  o  1.234,56
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return Decimal(t).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"importe no reconocido «{texto}»")


def leer_csv(contenido: bytes) -> list[dict]:
    texto = contenido.decode("utf-8-sig", errors="replace")
    muestra = texto[:2000]
    delim = ";" if muestra.count(";") > muestra.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto), delimiter=delim)
    if not lector.fieldnames:
        raise ErrorNegocio("VALIDACION", "El archivo está vacío o no tiene encabezados")
    mapa = {}
    for campo in lector.fieldnames:
        clave = campo.strip().lower()
        for destino, nombres in ALIAS.items():
            if clave in nombres:
                mapa[destino] = campo
    if "fecha" not in mapa or "descripcion" not in mapa or not ("monto" in mapa or "deposito" in mapa or "retiro" in mapa):
        raise ErrorNegocio("VALIDACION", "El CSV debe tener las columnas fecha, descripcion y monto "
                                         "(o deposito/retiro). Encontré: " + ", ".join(lector.fieldnames))
    movimientos = []
    for n, r in enumerate(lector, start=2):
        if not any((v or "").strip() for v in r.values()):
            continue
        try:
            if "monto" in mapa:
                monto = _monto(r[mapa["monto"]])
            else:
                monto = _monto(r.get(mapa.get("deposito"), "") or "") - _monto(r.get(mapa.get("retiro"), "") or "")
            movimientos.append({"fecha": _fecha(r[mapa["fecha"]]), "descripcion": r[mapa["descripcion"]].strip(),
                                "referencia": (r.get(mapa.get("referencia"), "") or "").strip() or None, "monto": monto})
        except ValueError as e:
            raise ErrorNegocio("VALIDACION", f"Fila {n}: {e}")
    return [m for m in movimientos if m["monto"] != 0]


def importar(conn: Connection, cuenta_bancaria_id: int, nombre_archivo: str, contenido: bytes) -> dict:
    if not fila(conn, "SELECT id FROM cuentas_bancarias WHERE id = :id", id=cuenta_bancaria_id):
        raise ErrorNegocio("NO_ENCONTRADO", "La cuenta bancaria no existe")
    movimientos = leer_csv(contenido)
    imp_id = valor(conn, "INSERT INTO importaciones_banco (cuenta_bancaria_id, archivo, filas) VALUES (:c, :a, :f) RETURNING id",
                   c=cuenta_bancaria_id, a=nombre_archivo, f=len(movimientos))
    nuevos, vistos = 0, {}
    for m in movimientos:
        base = f"{m['fecha']}|{m['descripcion']}|{m['referencia']}|{m['monto']}"
        vistos[base] = vistos.get(base, 0) + 1          # dos filas idénticas el mismo día son dos movimientos
        huella = hashlib.sha1(f"{base}|{vistos[base]}".encode()).hexdigest()
        r = conn.execute(text("""
            INSERT INTO movimientos_banco (cuenta_bancaria_id, importacion_id, fecha, descripcion, referencia, monto, huella)
            VALUES (:c, :i, :f, :d, :r, :m, :h) ON CONFLICT (cuenta_bancaria_id, huella) DO NOTHING"""),
            {"c": cuenta_bancaria_id, "i": imp_id, "f": m["fecha"], "d": m["descripcion"], "r": m["referencia"],
             "m": m["monto"], "h": huella})
        nuevos += r.rowcount
    duplicadas = len(movimientos) - nuevos
    conn.execute(text("UPDATE importaciones_banco SET duplicadas = :d WHERE id = :i"), {"d": duplicadas, "i": imp_id})
    return {"importacion_id": imp_id, "leidas": len(movimientos), "nuevas": nuevos, "duplicadas": duplicadas}


def lineas_libros_pendientes(conn: Connection, cuenta_bancaria_id: int) -> list[dict]:
    return filas(conn, """
        SELECT m.linea_id, m.fecha, m.folio, m.concepto, m.descripcion, (m.debe_base - m.haber_base) AS monto,
               (SELECT referencia FROM pagos WHERE poliza_id = m.poliza_id LIMIT 1) AS referencia_pago
          FROM v_movimientos m
          JOIN cuentas_bancarias b ON b.cuenta_id = m.cuenta_id AND b.id = :c
         WHERE NOT EXISTS (SELECT 1 FROM movimientos_banco mb WHERE mb.linea_id = m.linea_id)
         ORDER BY m.fecha, m.folio""", c=cuenta_bancaria_id)


def movimientos_banco(conn: Connection, cuenta_bancaria_id: int, solo_pendientes: bool = False) -> list[dict]:
    return filas(conn, """
        SELECT mb.*, m.folio, m.concepto AS concepto_poliza
          FROM movimientos_banco mb LEFT JOIN v_movimientos m ON m.linea_id = mb.linea_id
         WHERE mb.cuenta_bancaria_id = :c AND (NOT :p OR mb.linea_id IS NULL)
         ORDER BY mb.fecha, mb.id""", c=cuenta_bancaria_id, p=solo_pendientes)


def _contiene_referencia(ref: str | None, linea: dict) -> bool:
    if not ref:
        return False
    ref = ref.lower()
    textos = (linea.get("concepto"), linea.get("descripcion"), linea.get("referencia_pago"), linea.get("folio"))
    return any(t and ref in t.lower() for t in textos)


def conciliar_automatico(conn: Connection, cuenta_bancaria_id: int, tolerancia_dias: int = 3) -> dict:
    banco = movimientos_banco(conn, cuenta_bancaria_id, solo_pendientes=True)
    libros = lineas_libros_pendientes(conn, cuenta_bancaria_id)
    usados, parejas = set(), []

    def emparejar(mov, linea, motivo):
        usados.add(linea["linea_id"])
        parejas.append((mov["id"], linea["linea_id"], motivo))

    pendientes = []
    for mov in banco:                                       # pasada 1: importe + referencia
        candidatos = [l for l in libros if l["linea_id"] not in usados and l["monto"] == mov["monto"]
                      and abs((l["fecha"] - mov["fecha"]).days) <= max(tolerancia_dias, 10)
                      and _contiene_referencia(mov["referencia"], l)]
        if len(candidatos) == 1:
            emparejar(mov, candidatos[0], "importe y referencia")
        else:
            pendientes.append(mov)
    for mov in pendientes:                                  # pasada 2: importe + fecha cercana sin empate
        candidatos = [l for l in libros if l["linea_id"] not in usados and l["monto"] == mov["monto"]
                      and abs((l["fecha"] - mov["fecha"]).days) <= tolerancia_dias]
        if not candidatos:
            continue
        candidatos.sort(key=lambda l: abs((l["fecha"] - mov["fecha"]).days))
        if len(candidatos) > 1 and abs((candidatos[0]["fecha"] - mov["fecha"]).days) == abs((candidatos[1]["fecha"] - mov["fecha"]).days):
            continue                                        # empate: mejor que lo decida una persona
        emparejar(mov, candidatos[0], "importe y fecha")

    for mov_id, linea_id, _ in parejas:
        conn.execute(text("UPDATE movimientos_banco SET linea_id = :l, conciliado_en = now() WHERE id = :m"),
                     {"l": linea_id, "m": mov_id})
    return {"emparejados": len(parejas), "pendientes_banco": len(banco) - len(parejas),
            "detalle": [{"movimiento_id": m, "linea_id": l, "criterio": c} for m, l, c in parejas]}


def emparejar_manual(conn: Connection, movimiento_id: int, linea_id: int) -> dict:
    mov = fila(conn, "SELECT * FROM movimientos_banco WHERE id = :id", id=movimiento_id)
    if mov is None:
        raise ErrorNegocio("NO_ENCONTRADO", "El movimiento bancario no existe")
    if mov["linea_id"]:
        raise ErrorNegocio("VALIDACION", "Ese movimiento ya está conciliado")
    linea = next((l for l in lineas_libros_pendientes(conn, mov["cuenta_bancaria_id"]) if l["linea_id"] == linea_id), None)
    if linea is None:
        raise ErrorNegocio("VALIDACION", "El movimiento de libros no existe, no es de esta cuenta o ya está conciliado")
    if linea["monto"] != mov["monto"]:
        raise ErrorNegocio("VALIDACION", f"Los importes no coinciden: banco {mov['monto']:,.2f} y libros {linea['monto']:,.2f}")
    conn.execute(text("UPDATE movimientos_banco SET linea_id = :l, conciliado_en = now() WHERE id = :m"),
                 {"l": linea_id, "m": movimiento_id})
    return fila(conn, "SELECT * FROM movimientos_banco WHERE id = :id", id=movimiento_id)


def desemparejar(conn: Connection, movimiento_id: int):
    conn.execute(text("UPDATE movimientos_banco SET linea_id = NULL, conciliado_en = NULL WHERE id = :m"), {"m": movimiento_id})


def registrar_desde_banco(conn: Connection, movimiento_id: int, cuenta_id: int, concepto: str | None, usuario: str) -> dict:
    """Para cargos que solo aparecen en el banco (comisiones, intereses): crea la póliza y la concilia."""
    mov = fila(conn, """SELECT mb.*, b.cuenta_id AS cuenta_banco_id FROM movimientos_banco mb
                        JOIN cuentas_bancarias b ON b.id = mb.cuenta_bancaria_id WHERE mb.id = :id""", id=movimiento_id)
    if mov is None:
        raise ErrorNegocio("NO_ENCONTRADO", "El movimiento bancario no existe")
    if mov["linea_id"]:
        raise ErrorNegocio("VALIDACION", "Ese movimiento ya está conciliado")
    importe = abs(mov["monto"])
    banco = {"cuenta_id": mov["cuenta_banco_id"], "descripcion": mov["descripcion"]}
    otra = {"cuenta_id": cuenta_id, "descripcion": mov["descripcion"]}
    if mov["monto"] > 0:
        banco["debe"], otra["haber"] = importe, importe
    else:
        otra["debe"], banco["haber"] = importe, importe
    poliza = srv_polizas.crear_poliza(conn, {
        "tipo": "ingreso" if mov["monto"] > 0 else "egreso", "fecha": mov["fecha"], "contabilizar": True,
        "concepto": concepto or f"Movimiento bancario: {mov['descripcion']}", "lineas": [banco, otra],
    }, usuario)
    linea_banco = next(l for l in poliza["lineas"] if l["cuenta_id"] == mov["cuenta_banco_id"])
    conn.execute(text("UPDATE movimientos_banco SET linea_id = :l, conciliado_en = now() WHERE id = :m"),
                 {"l": linea_banco["id"], "m": movimiento_id})
    return poliza


def reporte(conn: Connection, cuenta_bancaria_id: int, corte: date) -> dict:
    cb = fila(conn, "SELECT b.*, c.codigo, c.nombre AS cuenta_nombre FROM cuentas_bancarias b JOIN cuentas c ON c.id = b.cuenta_id WHERE b.id = :id",
              id=cuenta_bancaria_id)
    if cb is None:
        raise ErrorNegocio("NO_ENCONTRADO", "La cuenta bancaria no existe")
    saldo_libros = valor(conn, """SELECT coalesce(sum(debe_base - haber_base), 0) FROM v_movimientos
                                  WHERE cuenta_id = :c AND fecha <= :f""", c=cb["cuenta_id"], f=corte)
    saldo_banco = valor(conn, "SELECT coalesce(sum(monto), 0) FROM movimientos_banco WHERE cuenta_bancaria_id = :c AND fecha <= :f",
                        c=cuenta_bancaria_id, f=corte)
    solo_banco = filas(conn, """SELECT id, fecha, descripcion, referencia, monto FROM movimientos_banco
                                WHERE cuenta_bancaria_id = :c AND fecha <= :f AND linea_id IS NULL ORDER BY fecha""",
                       c=cuenta_bancaria_id, f=corte)
    solo_libros = [l for l in lineas_libros_pendientes(conn, cuenta_bancaria_id) if l["fecha"] <= corte]
    ajuste_banco = sum((m["monto"] for m in solo_banco), CERO)
    ajuste_libros = sum((l["monto"] for l in solo_libros), CERO)
    return {"cuenta": cb, "corte": corte, "saldo_libros": saldo_libros, "saldo_banco": saldo_banco,
            "solo_banco": solo_banco, "solo_libros": solo_libros,
            "saldo_libros_conciliado": saldo_libros + ajuste_banco,
            "saldo_banco_conciliado": saldo_banco + ajuste_libros,
            "cuadra": saldo_libros + ajuste_banco == saldo_banco + ajuste_libros}
