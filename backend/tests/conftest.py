"""Pruebas contra un PostgreSQL REAL (base contabilidad_test), porque las reglas viven en
triggers y funciones de PostgreSQL: probarlas con SQLite no probaría nada.

Cada prueba corre dentro de una transacción que se deshace al final, así ninguna
prueba ensucia a la siguiente y todas parten del mismo catálogo base.
"""
import os
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.db import aplicar_migraciones, get_conn
from app.main import app
from app.seed import cargar_base
from app.seguridad import crear_token

_env = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
URL = os.getenv("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")
D = Decimal


@pytest.fixture(scope="session")
def engine():
    if not URL:
        pytest.skip("Define TEST_DATABASE_URL en backend/.env para correr las pruebas")
    eng = create_engine(URL, future=True)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    aplicar_migraciones(eng)
    with eng.begin() as c:
        cargar_base(c)
        # tipos de cambio fijos para pruebas de multimoneda
        c.execute(text("INSERT INTO tipos_cambio (moneda, fecha, tasa) VALUES "
                       "('EUR', '2026-01-01', 1.10), ('EUR', '2026-03-01', 1.20)"))
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine):
    c = engine.connect()
    t = c.begin()
    yield c
    t.rollback()
    c.close()


@pytest.fixture
def cliente(conn):
    """Cliente HTTP de la API que trabaja sobre la misma transacción de la prueba."""
    def _get_conn():
        sp = conn.begin_nested()
        try:
            yield conn
            sp.commit()
        except Exception:
            sp.rollback()
            raise

    app.dependency_overrides[get_conn] = _get_conn
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {crear_token({'usuario': 'admin', 'rol': 'admin'})}"
    yield c
    app.dependency_overrides.clear()


@contextmanager
def falla_con(conn, fragmento: str):
    """Ejecuta un bloque que DEBE fallar (dentro de un savepoint) y verifica el mensaje."""
    sp = conn.begin_nested()
    with pytest.raises(Exception) as info:
        yield
        conn.execute(text("SELECT 1"))
    sp.rollback()
    assert fragmento in str(info.value), f"se esperaba «{fragmento}» y llegó: {info.value}"


@pytest.fixture
def cta(conn):
    """Busca ids de cuentas por código: cta('1.1.03')"""
    def buscar(codigo: str) -> int:
        return conn.execute(text("SELECT id FROM cuentas WHERE codigo = :c"), {"c": codigo}).scalar_one()
    return buscar


@pytest.fixture
def banco_id(conn):
    return conn.execute(text("SELECT id FROM cuentas_bancarias LIMIT 1")).scalar_one()


@pytest.fixture
def poliza(conn, cta):
    """Crea y contabiliza una póliza sencilla: poliza(fecha, [(codigo, debe, haber), ...])"""
    from app.servicios import polizas

    def crear(fecha: date, renglones, concepto="Prueba", contabilizar=True, moneda=None, tipo_cambio=None):
        lineas = [{"cuenta_id": cta(c), "debe": D(str(de)), "haber": D(str(ha))} for c, de, ha in renglones]
        return polizas.crear_poliza(conn, {"fecha": fecha, "concepto": concepto, "lineas": lineas, "contabilizar": contabilizar,
                                           "moneda": moneda, "tipo_cambio": tipo_cambio}, "pruebas")
    return crear
