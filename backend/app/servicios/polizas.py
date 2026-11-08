"""Pólizas: captura en borrador, contabilización y reversa.

La validación de partida doble se hace dos veces a propósito:
  1. Aquí, para dar un mensaje inmediato y claro al usuario.
  2. En PostgreSQL (contabilizar_poliza), que es la garantía final: ningún
     camino (API, script, consola SQL) puede dejar una póliza descuadrada.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import fila, filas, valor
from app.errores import ErrorNegocio

CERO = Decimal("0.00")


def moneda_base(conn: Connection) -> str:
    return valor(conn, "SELECT moneda_base FROM empresa")


def resolver_tipo_cambio(conn: Connection, moneda: str | None, fecha: date, tipo_cambio: Decimal | None):
    base = moneda_base(conn)
    moneda = (moneda or base).upper()
    if moneda == base:
        return moneda, Decimal("1")
    if tipo_cambio is not None:
        return moneda, Decimal(tipo_cambio)
    return moneda, Decimal(valor(conn, "SELECT tipo_cambio_en(:m, :f)", m=moneda, f=fecha))


def validar_partida_doble(lineas: list[dict]) -> tuple[Decimal, Decimal]:
    """Reglas de una póliza cuadrada. Devuelve (total_debe, total_haber)."""
    if len(lineas) < 2:
        raise ErrorNegocio("DESCUADRE", "Una póliza necesita al menos dos líneas (un cargo y un abono)")
    for i, l in enumerate(lineas, start=1):
        debe, haber = Decimal(l.get("debe") or 0), Decimal(l.get("haber") or 0)
        if debe < 0 or haber < 0:
            raise ErrorNegocio("VALIDACION", f"Línea {i}: los importes no pueden ser negativos")
        if (debe > 0) == (haber > 0):
            raise ErrorNegocio("VALIDACION", f"Línea {i}: debe tener un importe en el debe o en el haber (solo uno)")
    total_debe = sum((Decimal(l.get("debe") or 0) for l in lineas), CERO)
    total_haber = sum((Decimal(l.get("haber") or 0) for l in lineas), CERO)
    if total_debe != total_haber:
        raise ErrorNegocio(
            "DESCUADRE",
            f"La póliza no cuadra: debe {total_debe:,.2f} y haber {total_haber:,.2f} "
            f"(diferencia {total_debe - total_haber:,.2f})",
        )
    return total_debe, total_haber


def _insertar_lineas(conn: Connection, poliza_id: int, lineas: list[dict]):
    for orden, l in enumerate(lineas, start=1):
        conn.execute(
            _sql_linea,
            {"p": poliza_id, "o": orden, "c": l["cuenta_id"], "d": l.get("descripcion"),
             "de": Decimal(l.get("debe") or 0), "ha": Decimal(l.get("haber") or 0)},
        )


_sql_linea = text(
    "INSERT INTO poliza_lineas (poliza_id, orden, cuenta_id, descripcion, debe, haber) "
    "VALUES (:p, :o, :c, :d, :de, :ha)"
)


def crear_poliza(conn: Connection, datos: dict, usuario: str, origen: str = "manual") -> dict:
    lineas = datos["lineas"]
    if datos.get("contabilizar"):
        validar_partida_doble(lineas)
    moneda, tc = resolver_tipo_cambio(conn, datos.get("moneda"), datos["fecha"], datos.get("tipo_cambio"))
    pid = valor(
        conn,
        "INSERT INTO polizas (tipo, fecha, concepto, moneda, tipo_cambio, origen, creado_por) "
        "VALUES (:t, :f, :c, :m, :tc, :o, :u) RETURNING id",
        t=datos.get("tipo", "diario"), f=datos["fecha"], c=datos["concepto"].strip(), m=moneda, tc=tc,
        o=origen, u=usuario,
    )
    _insertar_lineas(conn, pid, lineas)
    if datos.get("contabilizar"):
        contabilizar(conn, pid)
    return obtener(conn, pid)


def actualizar_borrador(conn: Connection, poliza_id: int, datos: dict, usuario: str) -> dict:
    actual = fila(conn, "SELECT estado FROM polizas WHERE id = :id", id=poliza_id)
    if actual is None:
        raise ErrorNegocio("NO_ENCONTRADO", "La póliza no existe")
    if actual["estado"] != "borrador":
        raise ErrorNegocio("INMUTABLE", f"La póliza está {actual['estado']}: solo se editan borradores")
    if datos.get("contabilizar"):
        validar_partida_doble(datos["lineas"])
    moneda, tc = resolver_tipo_cambio(conn, datos.get("moneda"), datos["fecha"], datos.get("tipo_cambio"))
    conn.execute(
        text("UPDATE polizas SET tipo=:t, fecha=:f, concepto=:c, moneda=:m, tipo_cambio=:tc WHERE id=:id"),
        {"t": datos.get("tipo", "diario"), "f": datos["fecha"], "c": datos["concepto"].strip(),
         "m": moneda, "tc": tc, "id": poliza_id},
    )
    conn.execute(text("DELETE FROM poliza_lineas WHERE poliza_id = :id"), {"id": poliza_id})
    _insertar_lineas(conn, poliza_id, datos["lineas"])
    if datos.get("contabilizar"):
        contabilizar(conn, poliza_id)
    return obtener(conn, poliza_id)


def contabilizar(conn: Connection, poliza_id: int) -> dict:
    lineas = filas(conn, "SELECT debe, haber FROM poliza_lineas WHERE poliza_id = :id", id=poliza_id)
    validar_partida_doble(lineas)
    conn.execute(text("SELECT contabilizar_poliza(:id)"), {"id": poliza_id})
    return obtener(conn, poliza_id)


def revertir(conn: Connection, poliza_id: int, fecha: date, motivo: str, usuario: str) -> dict:
    reversa_id = valor(conn, "SELECT (revertir_poliza(:id, :f, :m, :u)).id", id=poliza_id, f=fecha, m=motivo, u=usuario)
    return obtener(conn, reversa_id)


def eliminar_borrador(conn: Connection, poliza_id: int):
    p = fila(conn, "SELECT estado FROM polizas WHERE id = :id", id=poliza_id)
    if p is None:
        raise ErrorNegocio("NO_ENCONTRADO", "La póliza no existe")
    # El trigger rechaza el DELETE si no es borrador; aquí solo damos el mensaje primero.
    if p["estado"] != "borrador":
        raise ErrorNegocio("INMUTABLE", "Una póliza contabilizada no se borra: se cancela con una póliza de reversa")
    conn.execute(text("DELETE FROM polizas WHERE id = :id"), {"id": poliza_id})


def obtener(conn: Connection, poliza_id: int) -> dict:
    p = fila(conn, """
        SELECT p.*, CASE WHEN p.numero IS NULL THEN NULL ELSE p.anio || '-' || lpad(p.numero::text, 5, '0') END AS folio,
               r.anio || '-' || lpad(r.numero::text, 5, '0') AS folio_reversa_de,
               c.anio || '-' || lpad(c.numero::text, 5, '0') AS folio_cancelada_por,
               periodo_cerrado(p.fecha) AS periodo_cerrado
          FROM polizas p
          LEFT JOIN polizas r ON r.id = p.reversa_de
          LEFT JOIN polizas c ON c.id = p.cancelada_por
         WHERE p.id = :id""", id=poliza_id)
    if p is None:
        raise ErrorNegocio("NO_ENCONTRADO", "La póliza no existe")
    p["lineas"] = filas(conn, """
        SELECT l.id, l.orden, l.cuenta_id, c.codigo AS cuenta_codigo, c.nombre AS cuenta_nombre, l.descripcion,
               l.debe, l.haber, l.debe_base, l.haber_base
          FROM poliza_lineas l JOIN cuentas c ON c.id = l.cuenta_id
         WHERE l.poliza_id = :id ORDER BY l.orden, l.id""", id=poliza_id)
    p["total_debe"] = sum((l["debe"] for l in p["lineas"]), CERO)
    p["total_haber"] = sum((l["haber"] for l in p["lineas"]), CERO)
    return p


def listar(conn: Connection, desde: date | None, hasta: date | None, estado: str | None, q: str | None,
           limite: int = 200) -> list[dict]:
    return filas(conn, """
        SELECT p.id, p.tipo, p.fecha, p.concepto, p.estado, p.origen, p.moneda,
               CASE WHEN p.numero IS NULL THEN NULL ELSE p.anio || '-' || lpad(p.numero::text, 5, '0') END AS folio,
               coalesce(sum(l.debe), 0) AS total
          FROM polizas p LEFT JOIN poliza_lineas l ON l.poliza_id = p.id
         WHERE (CAST(:desde AS date) IS NULL OR p.fecha >= :desde)
           AND (CAST(:hasta AS date) IS NULL OR p.fecha <= :hasta)
           AND (CAST(:estado AS text) IS NULL OR p.estado = :estado)
           AND (CAST(:q AS text) IS NULL OR p.concepto ILIKE '%' || :q || '%'
                OR (p.anio || '-' || lpad(p.numero::text, 5, '0')) ILIKE '%' || :q || '%')
         GROUP BY p.id
         ORDER BY p.fecha DESC, p.numero DESC NULLS FIRST, p.id DESC
         LIMIT :lim""", desde=desde, hasta=hasta, estado=estado, q=q or None, lim=limite)
