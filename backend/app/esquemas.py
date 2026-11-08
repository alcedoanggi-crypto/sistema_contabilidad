"""Esquemas de entrada de la API (Pydantic). Los montos son Decimal, nunca float."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Monto = Decimal


def _dos_decimales(v: Decimal) -> Decimal:
    if v is None:
        return v
    if v.as_tuple().exponent < -2:
        raise ValueError("los montos admiten como máximo 2 decimales")
    return v


class Login(BaseModel):
    usuario: str
    password: str


class LineaPoliza(BaseModel):
    cuenta_id: int
    descripcion: str | None = None
    debe: Monto = Decimal("0")
    haber: Monto = Decimal("0")

    _v = field_validator("debe", "haber")(_dos_decimales)


class PolizaEntrada(BaseModel):
    tipo: Literal["diario", "ingreso", "egreso"] = "diario"
    fecha: date
    concepto: str = Field(min_length=1, max_length=300)
    moneda: str | None = None
    tipo_cambio: Decimal | None = None
    lineas: list[LineaPoliza]
    contabilizar: bool = False


class Reversa(BaseModel):
    fecha: date
    motivo: str = Field(min_length=3)


class CuentaEntrada(BaseModel):
    codigo: str
    nombre: str = Field(min_length=2)
    padre_id: int | None = None
    tipo: Literal["activo", "pasivo", "capital", "ingreso", "gasto"] | None = None
    naturaleza: Literal["deudora", "acreedora"] | None = None


class CuentaEdicion(BaseModel):
    nombre: str = Field(min_length=2)
    activa: bool = True


class TerceroEntrada(BaseModel):
    tipo: Literal["cliente", "proveedor", "ambos"]
    nombre: str = Field(min_length=2)
    rfc: str | None = None
    email: str | None = None
    telefono: str | None = None
    dias_credito: int = Field(30, ge=0, le=365)
    activo: bool = True


class ImpuestoEdicion(BaseModel):
    nombre: str
    tasa: Decimal = Field(ge=0, le=100)
    activo: bool = True


class LineaFactura(BaseModel):
    descripcion: str = Field(min_length=1)
    cuenta_id: int
    cantidad: Decimal = Field(gt=0)
    precio_unitario: Decimal = Field(ge=0)


class FacturaEntrada(BaseModel):
    tipo: Literal["ingreso", "gasto"]
    folio: str = Field(min_length=1)
    tercero_id: int
    fecha: date
    vencimiento: date | None = None
    moneda: str | None = None
    tipo_cambio: Decimal | None = None
    lineas: list[LineaFactura] = Field(min_length=1)
    impuestos: list[str] = []          # códigos: IVA16, RET_ISR10...
    notas: str | None = None


class PagoEntrada(BaseModel):
    fecha: date
    monto: Monto = Field(gt=0)
    cuenta_bancaria_id: int
    referencia: str | None = None

    _v = field_validator("monto")(_dos_decimales)


class TipoCambioEntrada(BaseModel):
    moneda: str
    fecha: date
    tasa: Decimal = Field(gt=0)


class Reapertura(BaseModel):
    motivo: str = Field(min_length=3)


class Emparejar(BaseModel):
    linea_id: int


class RegistroDesdeBanco(BaseModel):
    cuenta_id: int                  # cuenta de contrapartida (p. ej. comisiones bancarias)
    concepto: str | None = None
