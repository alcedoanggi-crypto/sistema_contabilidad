"""Inicio de sesión con JWT y permisos por rol (admin, contador, consulta)."""
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.engine import Connection

from app.config import settings
from app.db import fila, get_conn

ALGORITMO = "HS256"
_bearer = HTTPBearer(auto_error=False)


def hash_password(clave: str) -> str:
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode()


def verificar_password(clave: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw(clave.encode(), hash_.encode())
    except ValueError:
        return False


def crear_token(usuario: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.token_horas)
    return jwt.encode({"sub": usuario["usuario"], "rol": usuario["rol"], "exp": exp}, settings.secret_key, ALGORITMO)


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                   conn: Connection = Depends(get_conn)) -> dict:
    no_autorizado = HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar")
    if cred is None:
        raise no_autorizado
    try:
        datos = jwt.decode(cred.credentials, settings.secret_key, algorithms=[ALGORITMO])
    except JWTError:
        raise no_autorizado
    u = fila(conn, "SELECT id, usuario, nombre, rol FROM usuarios WHERE usuario = :u AND activo", u=datos.get("sub"))
    if u is None:
        raise no_autorizado
    return u


def requiere_rol(*roles: str):
    def dependencia(u: dict = Depends(usuario_actual)) -> dict:
        if u["rol"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene permiso para esta acción")
        return u
    return dependencia


# Atajos: leer = cualquier usuario; escribir = contador o admin; administrar = solo admin
puede_leer = usuario_actual
puede_escribir = requiere_rol("admin", "contador")
solo_admin = requiere_rol("admin")
