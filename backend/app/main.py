"""Sistema de Contabilidad — API (FastAPI)."""
from decimal import Decimal

from fastapi import FastAPI
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.errores import ErrorNegocio, manejar_bd, manejar_negocio
from app.rutas import contabilidad, operaciones, reportes

# Los montos viajan como texto ("1234.50"), no como float de JavaScript: así no se pierde ningún centavo.
ENCODERS_BY_TYPE[Decimal] = str

app = FastAPI(title="Sistema de Contabilidad", version="1.0.0",
              description="Partida doble, libros, estados financieros, CxC/CxP, impuestos, multimoneda y conciliación bancaria.")

app.add_middleware(CORSMiddleware, allow_origins=settings.origenes, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])
app.add_exception_handler(ErrorNegocio, manejar_negocio)
app.add_exception_handler(DBAPIError, manejar_bd)

for r in (contabilidad.router, reportes.router, operaciones.router):
    app.include_router(r, prefix="/api")


@app.get("/api/salud")
def salud():
    return {"estado": "ok"}
