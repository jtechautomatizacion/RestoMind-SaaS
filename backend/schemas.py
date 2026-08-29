from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ============ PLATOS ============

class PlatoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    categoria: str = Field(..., min_length=1)
    precio_venta: float = Field(..., gt=0)
    descripcion: Optional[str] = None
    imagen_url: Optional[str] = None


class PlatoUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[str] = None
    precio_venta: Optional[float] = None
    descripcion: Optional[str] = None
    imagen_url: Optional[str] = None


class PlatoResponse(BaseModel):
    id: int
    cliente_id: str
    nombre: str
    categoria: str
    precio_venta: float
    descripcion: Optional[str]
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True


# ============ MESAS ============

class MesaCreate(BaseModel):
    numero: int
    capacidad: int = 4
    ubicacion: Optional[str] = None


class MesaResponse(BaseModel):
    id: int
    cliente_id: str
    numero: int
    capacidad: int
    ubicacion: Optional[str]
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True


# ============ COMANDAS ============

class ComandaPlatoCreate(BaseModel):
    plato_id: int
    cantidad: int = Field(default=1, gt=0)


class ComandaCreate(BaseModel):
    numero_mesa: int
    platos: List[ComandaPlatoCreate] = Field(..., min_items=1)


class ComandaPlatoResponse(BaseModel):
    plato_id: int
    nombre: str
    cantidad: int
    precio_unitario: float
    subtotal: float

    class Config:
        from_attributes = True


class ComandaResponse(BaseModel):
    id: int
    cliente_id: str
    numero_mesa: int
    estado: str
    total_cuenta: float
    platos: List[ComandaPlatoResponse]
    creado_en: datetime

    class Config:
        from_attributes = True


class ComandaEstadoUpdate(BaseModel):
    estado: str = Field(..., pattern="^(cocina|entregado|cobrado|cancelado)$")


# ============ COMPRAS ============

class CompraCreate(BaseModel):
    descripcion: str = Field(..., min_length=1, max_length=100)
    categoria: Optional[str] = None
    monto: float = Field(..., gt=0)
    fecha: str  # YYYY-MM-DD


class CompraUpdate(BaseModel):
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    monto: Optional[float] = None
    fecha: Optional[str] = None


class CompraResponse(BaseModel):
    id: int
    cliente_id: str
    descripcion: str
    categoria: Optional[str]
    monto: float
    fecha: str
    estado: str
    creado_por: Optional[str]
    creado_en: datetime

    class Config:
        from_attributes = True


# ============ MONITOREO ============

class MonitorCocinaItem(BaseModel):
    comanda_id: int
    numero_mesa: int
    platos: List[str]  # Nombres de platos
    creado_hace_minutos: int
    estado: str

    class Config:
        from_attributes = True
