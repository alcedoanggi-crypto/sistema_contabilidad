"""Datos de demostración.

Uso:
    python -m app.seed            # aplica migraciones y carga la demo si la base está vacía
    python -m app.seed --reset    # BORRA todo y vuelve a cargar la demo

Toda la demo se registra con los mismos servicios que usa la API (facturas, pagos,
pólizas), así que cumple las mismas reglas que una captura real.
"""
import csv
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import aplicar_migraciones, fila, get_engine, valor
from app.seguridad import hash_password
from app.servicios import conciliacion, facturas, polizas

USUARIO = "demo"
D = Decimal
CARPETA_EJEMPLOS = Path(__file__).resolve().parent.parent.parent / "docs" / "ejemplos"

CATALOGO = [
    # codigo, nombre, tipo, naturaleza (None = la del padre)
    ("1", "Activo", "activo", "deudora"),
    ("1.1", "Activo circulante", "activo", None),
    ("1.1.01", "Caja", "activo", None),
    ("1.1.02", "Bancos", "activo", None),
    ("1.1.02.01", "Banco Nacional · cuenta 4521", "activo", None),
    ("1.1.03", "Clientes", "activo", None),
    ("1.1.04", "IVA acreditable", "activo", None),
    ("1.1.05", "Impuestos retenidos a favor", "activo", None),
    ("1.2", "Activo no circulante", "activo", None),
    ("1.2.01", "Mobiliario y equipo", "activo", None),
    ("1.2.02", "Equipo de cómputo", "activo", None),
    ("1.2.03", "Depreciación acumulada", "activo", "acreedora"),
    ("2", "Pasivo", "pasivo", "acreedora"),
    ("2.1", "Pasivo a corto plazo", "pasivo", None),
    ("2.1.01", "Proveedores", "pasivo", None),
    ("2.1.02", "Acreedores diversos", "pasivo", None),
    ("2.1.03", "IVA trasladado", "pasivo", None),
    ("2.1.04", "Retenciones por pagar", "pasivo", None),
    ("2.1.05", "Sueldos por pagar", "pasivo", None),
    ("3", "Capital contable", "capital", "acreedora"),
    ("3.1", "Capital social", "capital", None),
    ("4", "Ingresos", "ingreso", "acreedora"),
    ("4.1", "Ventas", "ingreso", None),
    ("4.1.01", "Servicios de consultoría", "ingreso", None),
    ("4.1.02", "Desarrollo de software", "ingreso", None),
    ("4.2", "Otros ingresos", "ingreso", None),
    ("4.2.01", "Utilidad cambiaria", "ingreso", None),
    ("4.2.02", "Intereses ganados", "ingreso", None),
    ("5", "Gastos", "gasto", "deudora"),
    ("5.1", "Gastos de operación", "gasto", None),
    ("5.1.01", "Sueldos y salarios", "gasto", None),
    ("5.1.02", "Renta de oficina", "gasto", None),
    ("5.1.03", "Internet y telefonía", "gasto", None),
    ("5.1.04", "Papelería y artículos de oficina", "gasto", None),
    ("5.1.05", "Software y licencias", "gasto", None),
    ("5.1.06", "Depreciación", "gasto", None),
    ("5.1.07", "Publicidad", "gasto", None),
    ("5.2", "Gastos financieros", "gasto", None),
    ("5.2.01", "Comisiones bancarias", "gasto", None),
    ("5.2.02", "Pérdida cambiaria", "gasto", None),
]


def cargar_catalogo(conn: Connection) -> dict[str, int]:
    ids: dict[str, int] = {}
    for codigo, nombre, tipo, naturaleza in CATALOGO:
        padre = ids.get(codigo.rsplit(".", 1)[0]) if "." in codigo else None
        if naturaleza is None:
            naturaleza = valor(conn, "SELECT naturaleza FROM cuentas WHERE id = :id", id=padre)
        ids[codigo] = valor(conn, """INSERT INTO cuentas (codigo, nombre, tipo, naturaleza, padre_id)
                                     VALUES (:c, :n, :t, :na, :p) RETURNING id""",
                            c=codigo, n=nombre, t=tipo, na=naturaleza, p=padre)
    return ids


def cargar_base(conn: Connection) -> dict[str, int]:
    """Empresa, monedas, catálogo, impuestos, usuarios y banco: lo mínimo para operar (también lo usan las pruebas)."""
    conn.execute(text("INSERT INTO monedas VALUES ('USD', 'Dólar estadounidense', 'US$'), ('EUR', 'Euro', '€'), "
                      "('MXN', 'Peso mexicano', 'MX$')"))
    conn.execute(text("INSERT INTO empresa (nombre, rfc, moneda_base) VALUES ('Nexo Soluciones Digitales S.A.', 'NSD-260101-AB1', 'USD')"))
    c = cargar_catalogo(conn)
    conn.execute(text("""UPDATE empresa SET cuenta_clientes_id = :cl, cuenta_proveedores_id = :pr,
                                cuenta_utilidad_cambiaria_id = :ut, cuenta_perdida_cambiaria_id = :pe"""),
                 {"cl": c["1.1.03"], "pr": c["2.1.01"], "ut": c["4.2.01"], "pe": c["5.2.02"]})
    for codigo, nombre, tipo, tasa, ventas, compras in (
        ("IVA16", "IVA 16 %", "traslado", "16", "2.1.03", "1.1.04"),
        ("IVA0", "IVA 0 % (exportación)", "traslado", "0", "2.1.03", "1.1.04"),
        ("RET_ISR10", "Retención ISR 10 %", "retencion", "10", "1.1.05", "2.1.04"),
        ("RET_IVA", "Retención IVA 2/3", "retencion", "10.6667", "1.1.05", "2.1.04"),
    ):
        conn.execute(text("""INSERT INTO impuestos (codigo, nombre, tipo, tasa, cuenta_ventas_id, cuenta_compras_id)
                             VALUES (:c, :n, :t, :ta, :v, :co)"""),
                     {"c": codigo, "n": nombre, "t": tipo, "ta": D(tasa), "v": c[ventas], "co": c[compras]})
    for usuario, nombre, rol, clave in (("admin", "Administradora", "admin", "admin123"),
                                        ("contador", "Contador General", "contador", "contador123"),
                                        ("consulta", "Auditor (solo lectura)", "consulta", "consulta123")):
        conn.execute(text("INSERT INTO usuarios (usuario, nombre, password_hash, rol) VALUES (:u, :n, :h, :r)"),
                     {"u": usuario, "n": nombre, "h": hash_password(clave), "r": rol})
    conn.execute(text("""INSERT INTO cuentas_bancarias (nombre, banco, numero, moneda, cuenta_id)
                         VALUES ('Cuenta operativa', 'Banco Nacional', '****4521', 'USD', :c)"""), {"c": c["1.1.02.01"]})
    return c


def _tipos_cambio(conn: Connection, desde: date, hasta: date, rnd: random.Random):
    eur, mxn = D("1.0850"), D("0.0545")
    dia = desde
    while dia <= hasta:
        if dia.weekday() < 5:                                   # se publican en días hábiles
            eur = (eur + D(str(rnd.uniform(-0.004, 0.0045)))).quantize(D("0.0001"))
            mxn = (mxn + D(str(rnd.uniform(-0.0003, 0.0003)))).quantize(D("0.000001"))
            conn.execute(text("INSERT INTO tipos_cambio (moneda, fecha, tasa) VALUES ('EUR', :f, :e), ('MXN', :f, :m)"),
                         {"f": dia, "e": eur, "m": mxn})
        dia += timedelta(days=1)


def _poliza(conn, fecha, concepto, lineas, tipo="diario", contabilizar=True):
    return polizas.crear_poliza(conn, {"tipo": tipo, "fecha": fecha, "concepto": concepto, "lineas": lineas,
                                       "contabilizar": contabilizar}, USUARIO)


def cargar_demo(conn: Connection):
    rnd = random.Random(7)
    c = cargar_base(conn)
    banco = fila(conn, "SELECT id, cuenta_id FROM cuentas_bancarias LIMIT 1")
    _tipos_cambio(conn, date(2026, 7, 20), date(2026, 11, 8), rnd)

    def tercero(tipo, nombre, rfc, dias):
        return valor(conn, """INSERT INTO terceros (tipo, nombre, rfc, email, dias_credito) VALUES (:t, :n, :r, :e, :d) RETURNING id""",
                     t=tipo, n=nombre, r=rfc, e=nombre.split()[0].lower() + "@correo.com", d=dias)

    cli = {
        "andes": tercero("cliente", "Comercial Andes S.A.", "CAN-850101-XY1", 30),
        "pacifico": tercero("cliente", "Logística del Pacífico", "LDP-900215-KL2", 30),
        "iberia": tercero("cliente", "Iberia Retail S.L. (España)", "ESB-12345678", 45),
        "clinica": tercero("cliente", "Clínica Santa Lucía", "CSL-010320-MN3", 15),
        "aurora": tercero("cliente", "Hotel Aurora", "HAU-110505-PQ4", 30),
    }
    prov = {
        "inmob": tercero("proveedor", "Inmobiliaria Torre Norte", "ITN-750607-RS5", 10),
        "net": tercero("proveedor", "FibraNet Telecom", "FNT-120909-TU6", 15),
        "tec": tercero("proveedor", "TecnoMayorista", "TMA-030303-VW7", 30),
        "cloud": tercero("proveedor", "CloudSoft Licencias", "CSL-140101-YZ8", 30),
        "papel": tercero("proveedor", "Papelería El Estudiante", "PEE-990909-AB9", 0),
    }

    # --- Apertura: aportación de capital
    _poliza(conn, date(2026, 8, 1), "Aportación inicial de capital de los socios",
            [{"cuenta_id": banco["cuenta_id"], "descripcion": "Depósito TRF-90001", "debe": D("50000.00")},
             {"cuenta_id": c["3.1"], "haber": D("50000.00")}], tipo="ingreso")

    ventas = []

    def venta(fecha, cliente, folio, desc, cuenta, cantidad, precio, impuestos=("IVA16",), moneda=None):
        f = facturas.crear_factura(conn, {"tipo": "ingreso", "folio": folio, "tercero_id": cli[cliente], "fecha": fecha,
                                          "moneda": moneda, "impuestos": list(impuestos),
                                          "lineas": [{"descripcion": desc, "cuenta_id": c[cuenta], "cantidad": D(cantidad),
                                                      "precio_unitario": D(precio)}]}, USUARIO)
        ventas.append(f)
        return f

    def compra(fecha, proveedor, folio, desc, cuenta, importe, impuestos=("IVA16",)):
        return facturas.crear_factura(conn, {"tipo": "gasto", "folio": folio, "tercero_id": prov[proveedor], "fecha": fecha,
                                             "impuestos": list(impuestos),
                                             "lineas": [{"descripcion": desc, "cuenta_id": c[cuenta], "cantidad": D("1"),
                                                         "precio_unitario": D(importe)}]}, USUARIO)

    ref = iter(range(10101, 10999))

    def pagar(factura, fecha, monto=None):
        saldo = facturas.saldo_factura(conn, factura["id"])
        return facturas.registrar_pago(conn, factura["id"], {"fecha": fecha, "monto": monto or saldo,
                                                             "cuenta_bancaria_id": banco["id"],
                                                             "referencia": f"TRF-{next(ref)}"}, USUARIO)

    # --- Compra de equipo (activo fijo)
    eq = compra(date(2026, 8, 3), "tec", "TM-4410", "3 laptops para el equipo de desarrollo", "1.2.02", "6000.00")
    pagar(eq, date(2026, 8, 5))

    meses = [(2026, 8), (2026, 9), (2026, 10), (2026, 11)]
    for anio, mes in meses:
        uno = date(anio, mes, 1)
        # Renta con retenciones de ISR e IVA (arrendamiento a persona física)
        renta = compra(uno + timedelta(days=1), "inmob", f"R-{mes:02d}{anio}", f"Renta de oficina {mes:02d}/{anio}", "5.1.02",
                       "1800.00", ("IVA16", "RET_ISR10", "RET_IVA"))
        internet = compra(uno + timedelta(days=4), "net", f"FN-{mes}{rnd.randint(100, 999)}", "Internet empresarial 300 Mbps",
                          "5.1.03", "220.00")
        if mes < 11:
            pagar(renta, uno + timedelta(days=5))
            pagar(internet, uno + timedelta(days=12))
        if mes in (8, 10):
            licencias = compra(uno + timedelta(days=8), "cloud", f"CS-{mes}77", "Licencias de software (suscripción)",
                               "5.1.05", "950.00")
            pagar(licencias, uno + timedelta(days=20))
        if mes == 9:
            compra(date(2026, 9, 18), "papel", "PE-3321", "Papelería y tóner", "5.1.04", "185.40")

        # Nómina quincenal (sueldos pagados por transferencia)
        if mes < 11:
            for dia in (15, 28):
                _poliza(conn, date(anio, mes, dia), f"Nómina quincenal {dia:02d}/{mes:02d}/{anio}",
                        [{"cuenta_id": c["5.1.01"], "descripcion": "Sueldos del personal", "debe": D("3750.00")},
                         {"cuenta_id": banco["cuenta_id"], "descripcion": f"Dispersión de nómina NOM-{mes}{dia}",
                          "haber": D("3750.00")}], tipo="egreso")
            # Depreciación mensual del equipo de cómputo (6,000 / 36 meses)
            fin = (uno.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            _poliza(conn, fin, f"Depreciación de equipo de cómputo {mes:02d}/{anio}",
                    [{"cuenta_id": c["5.1.06"], "debe": D("166.67")}, {"cuenta_id": c["1.2.03"], "haber": D("166.67")}])
        if mes in (8, 9):
            _poliza(conn, date(anio, mes, 30 if mes == 9 else 31), f"Comisión por manejo de cuenta {mes:02d}/{anio}",
                    [{"cuenta_id": c["5.2.01"], "debe": D("12.50")},
                     {"cuenta_id": banco["cuenta_id"], "descripcion": "Comisión manejo de cuenta", "haber": D("12.50")}],
                    tipo="egreso")

    # --- Ventas (con su cobro en distintos momentos para tener antigüedad de saldos)
    v = venta(date(2026, 8, 6), "andes", "A-1001", "Consultoría en procesos (agosto)", "4.1.01", "40", "95.00")
    pagar(v, date(2026, 9, 2))
    v = venta(date(2026, 8, 12), "pacifico", "A-1002", "Sistema de rastreo de flota (fase 1)", "4.1.02", "1", "8500.00")
    pagar(v, date(2026, 9, 10))
    v_clin = venta(date(2026, 8, 20), "clinica", "A-1003", "Mantenimiento del sistema de citas", "4.1.02", "1", "1200.00",
                   ("IVA16", "RET_ISR10"))   # sin pagar: queda vencida más de 60 días
    v = venta(date(2026, 8, 25), "iberia", "E-2001", "Desarrollo de tienda en línea (hito 1)", "4.1.02", "1", "6000.00",
              ("IVA0",), moneda="EUR")
    pagar(v, date(2026, 9, 28))                       # cobro en euros con otro tipo de cambio -> diferencia cambiaria
    v = venta(date(2026, 9, 4), "andes", "A-1004", "Consultoría en procesos (septiembre)", "4.1.01", "36", "95.00")
    pagar(v, date(2026, 10, 1))
    v = venta(date(2026, 9, 15), "aurora", "A-1005", "Página web y sistema de reservas", "4.1.02", "1", "4800.00")
    pagar(v, date(2026, 10, 6), D("2784.00"))         # pago parcial (la mitad)
    v = venta(date(2026, 9, 22), "pacifico", "A-1006", "Sistema de rastreo de flota (fase 2)", "4.1.02", "1", "7200.00")
    pagar(v, date(2026, 10, 20))
    v = venta(date(2026, 10, 3), "andes", "A-1007", "Consultoría en procesos (octubre)", "4.1.01", "42", "95.00")
    pagar(v, date(2026, 11, 2))
    venta(date(2026, 10, 10), "iberia", "E-2002", "Desarrollo de tienda en línea (hito 2)", "4.1.02", "1", "5500.00",
          ("IVA0",), moneda="EUR")
    cancelada = venta(date(2026, 10, 14), "clinica", "A-1008", "Capacitación al personal", "4.1.01", "8", "120.00")
    venta(date(2026, 10, 15), "clinica", "A-1009", "Capacitación al personal (corregida)", "4.1.01", "10", "120.00")
    venta(date(2026, 10, 28), "aurora", "A-1010", "Soporte mensual del sistema de reservas", "4.1.02", "1", "650.00")
    venta(date(2026, 11, 3), "pacifico", "A-1011", "Soporte y hosting (noviembre)", "4.1.02", "1", "900.00")
    venta(date(2026, 11, 5), "andes", "A-1012", "Consultoría en procesos (noviembre)", "4.1.01", "20", "95.00")

    facturas.cancelar_factura(conn, cancelada["id"], date(2026, 10, 15), "Cantidad de horas incorrecta; se refactura con A-1009",
                              USUARIO)

    # --- Una póliza capturada con error y corregida mediante reversa (inmutabilidad)
    erronea = _poliza(conn, date(2026, 10, 18), "Compra de artículos de oficina en efectivo",
                      [{"cuenta_id": c["5.1.07"], "descripcion": "Registrada por error en publicidad", "debe": D("64.00")},
                       {"cuenta_id": c["1.1.01"], "haber": D("64.00")}])
    polizas.revertir(conn, erronea["id"], date(2026, 10, 18), "Cuenta de gasto equivocada", USUARIO)
    _poliza(conn, date(2026, 10, 18), "Compra de artículos de oficina en efectivo (corregida)",
            [{"cuenta_id": c["5.1.04"], "debe": D("64.00")}, {"cuenta_id": c["1.1.01"], "haber": D("64.00")}])
    _poliza(conn, date(2026, 10, 2), "Fondo de caja chica",
            [{"cuenta_id": c["1.1.01"], "debe": D("300.00")},
             {"cuenta_id": banco["cuenta_id"], "descripcion": "Retiro para caja chica CHQ-0051", "haber": D("300.00")}],
            tipo="egreso")

    # --- Un borrador pendiente (aún no afecta saldos)
    _poliza(conn, date(2026, 11, 6), "Provisión de publicidad en redes (pendiente de revisar)",
            [{"cuenta_id": c["5.1.07"], "debe": D("400.00")}, {"cuenta_id": c["2.1.02"], "haber": D("400.00")}],
            contabilizar=False)

    # --- Estado de cuenta del banco (CSV) e importación + conciliación automática
    archivo = generar_estado_cuenta(conn, banco["cuenta_id"], rnd)
    conciliacion.importar(conn, banco["id"], archivo.name, archivo.read_bytes())
    conciliacion.conciliar_automatico(conn, banco["id"])

    # --- Cierre de agosto y septiembre
    conn.execute(text("SELECT cerrar_periodo(2026, 8, 'admin'), cerrar_periodo(2026, 9, 'admin')"))


def generar_estado_cuenta(conn: Connection, cuenta_banco_id: int, rnd: random.Random) -> Path:
    """Arma un estado de cuenta realista a partir de los movimientos del banco en libros:
    el banco los aplica 0-2 días después, cobra comisiones que aún no están en libros
    (octubre y noviembre) y no incluye el último pago (en tránsito)."""
    movs = [dict(r._mapping) for r in conn.execute(text("""
        SELECT m.fecha, m.concepto, m.descripcion, m.debe_base - m.haber_base AS monto,
               (SELECT referencia FROM pagos WHERE poliza_id = m.poliza_id LIMIT 1) AS referencia
          FROM v_movimientos m WHERE m.cuenta_id = :c AND m.fecha <= '2026-11-04' ORDER BY m.fecha, m.linea_id"""),
        {"c": cuenta_banco_id})]
    renglones = []
    for m in movs:
        texto = (m["descripcion"] or m["concepto"]).upper()
        referencia = m["referencia"] or next((p for p in texto.replace("·", " ").split() if "-" in p and p[0].isalpha()), "")
        if "COMISIÓN" in texto:
            referencia = "COM"
        renglones.append([m["fecha"] + timedelta(days=rnd.choice((0, 0, 1, 2))), texto[:60], referencia, m["monto"]])
    renglones.sort(key=lambda r: r[0])
    renglones.pop()                                                   # el último pago aún no llega al banco
    for fecha in (date(2026, 10, 31), date(2026, 11, 4)):
        renglones.append([fecha, "COMISION POR MANEJO DE CUENTA", "COM", D("-12.50")])
    renglones.append([date(2026, 10, 31), "INTERESES GANADOS", "INT", D("8.35")])
    renglones.sort(key=lambda r: r[0])

    CARPETA_EJEMPLOS.mkdir(parents=True, exist_ok=True)
    ruta = CARPETA_EJEMPLOS / "estado_cuenta_banco_nacional.csv"
    with ruta.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fecha", "descripcion", "referencia", "monto"])
        for fecha, desc, refe, monto in renglones:
            w.writerow([fecha.isoformat(), desc, refe, f"{monto:.2f}"])
    return ruta


def reiniciar(engine=None):
    engine = engine or get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    aplicar_migraciones(engine)


def main():
    engine = get_engine()
    if "--reset" in sys.argv:
        reiniciar(engine)
        print("Base reiniciada.")
    else:
        aplicar_migraciones(engine)
    with engine.begin() as conn:
        if valor(conn, "SELECT count(*) FROM empresa"):
            print("La base ya tiene datos; usa --reset para recargar la demo.")
            return
        cargar_demo(conn)
        n = valor(conn, "SELECT count(*) FROM polizas")
        print(f"Demo cargada: {n} pólizas, {valor(conn, 'SELECT count(*) FROM facturas')} facturas.")


if __name__ == "__main__":
    main()
