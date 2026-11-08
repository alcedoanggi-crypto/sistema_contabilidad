"""Traduce los errores de negocio (propios o de PostgreSQL) a respuestas HTTP claras."""
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError

# Prefijo del mensaje que lanzan los triggers/funciones de sql/  ->  código HTTP
CODIGOS = {
    "DESCUADRE": 422,
    "VALIDACION": 422,
    "CATALOGO": 422,
    "TIPO_CAMBIO": 422,
    "INMUTABLE": 409,
    "PERIODO_CERRADO": 409,
    "NO_ENCONTRADO": 404,
}


class ErrorNegocio(Exception):
    def __init__(self, codigo: str, mensaje: str, estado: int | None = None):
        self.codigo = codigo
        self.mensaje = mensaje
        self.estado = estado or CODIGOS.get(codigo, 422)
        super().__init__(f"{codigo}: {mensaje}")


def desde_bd(exc: DBAPIError) -> ErrorNegocio | None:
    """Si el error viene de una regla de la base (RAISE EXCEPTION 'CODIGO: ...'), lo convierte."""
    original = getattr(exc, "orig", None)
    diag = getattr(original, "diag", None)
    mensaje = (getattr(diag, "message_primary", None) or str(original or exc)).strip()
    if ":" in mensaje:
        codigo, resto = mensaje.split(":", 1)
        if codigo in CODIGOS:
            return ErrorNegocio(codigo, resto.strip())
    if isinstance(exc, IntegrityError):
        detalle = getattr(diag, "message_detail", None) or mensaje
        if "duplicate key" in mensaje or "llave duplicada" in mensaje:
            return ErrorNegocio("VALIDACION", f"Ya existe un registro con esos datos ({detalle})", 409)
        return ErrorNegocio("VALIDACION", f"Datos inválidos: {mensaje}")
    return None


async def manejar_negocio(_: Request, exc: ErrorNegocio):
    return JSONResponse(status_code=exc.estado, content={"codigo": exc.codigo, "detail": exc.mensaje})


async def manejar_bd(_: Request, exc: DBAPIError):
    err = desde_bd(exc)
    if err is None:
        raise exc
    return JSONResponse(status_code=err.estado, content={"codigo": err.codigo, "detail": err.mensaje})
