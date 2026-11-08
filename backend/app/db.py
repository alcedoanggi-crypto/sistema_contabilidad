"""Conexión a PostgreSQL y migraciones.

Se usa SQLAlchemy Core con SQL explícito: las reglas contables viven en
PostgreSQL (triggers y funciones de sql/), y Python solo orquesta.
"""
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.config import settings

CARPETA_SQL = Path(__file__).resolve().parent.parent / "sql"

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_conn():
    """Dependencia de FastAPI: una transacción por petición (commit al final, rollback si falla)."""
    with get_engine().begin() as conn:
        yield conn


def aplicar_migraciones(engine: Engine | None = None) -> list[str]:
    """Aplica en orden los archivos sql/NNN_*.sql que aún no se hayan aplicado."""
    engine = engine or get_engine()
    aplicadas = []
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migraciones (archivo text PRIMARY KEY, aplicado_en timestamptz DEFAULT now())"
        ))
        hechas = {r[0] for r in conn.execute(text("SELECT archivo FROM schema_migraciones"))}
        for archivo in sorted(CARPETA_SQL.glob("[0-9][0-9][0-9]_*.sql")):
            if archivo.name in hechas:
                continue
            # Directo al driver y sin parámetros: los '%' de los RAISE de PL/pgSQL no son placeholders
            conn.connection.driver_connection.execute(archivo.read_text(encoding="utf-8"))
            conn.execute(text("INSERT INTO schema_migraciones (archivo) VALUES (:a)"), {"a": archivo.name})
            aplicadas.append(archivo.name)
    return aplicadas


def filas(conn: Connection, sql: str, **params) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def fila(conn: Connection, sql: str, **params) -> dict | None:
    r = conn.execute(text(sql), params).first()
    return dict(r._mapping) if r else None


def valor(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params).scalar()
