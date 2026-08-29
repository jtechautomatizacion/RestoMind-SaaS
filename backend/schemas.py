from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ============ GENÉRICO ============

class EstadoUpdate(BaseModel):
    """Payload genérico para PATCH /.../estado. Cada ruta valida los valores permitidos."""
    estado: str = Field(..., min_length=1)


# ============ PLATOS ============

class PlatoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    categoria: str = Field(..., min_length=1, max_length=50)
    precio_venta: float = Field(..., gt=0)
    descripcion: Optional[str] = Field(default=None, max_length=300)


class PlatoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    categoria: Optional[str] = Field(default=None, min_length=1, max_length=50)
    precio_venta: Optional[float] = Field(default=None, gt=0)
    descripcion: Optional[str] = Field(default=None, max_length=300)


class PlatoResponse(BaseModel):
    id: int
    cliente_id: str
    nombre: str
    categoria: str
    precio_venta: float
    descripcion: Optional[str] = None
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True


# ============ MESAS ============

class MesaCreate(BaseModel):
    numero: int = Field(..., gt=0)
    capacidad: int = Field(default=4, gt=0, le=50)
    ubicacion: Optional[str] = Field(default=None, max_length=50)


class MesaResponse(BaseModel):
    id: int
    cliente_id: str
    numero: int
    capacidad: int
    ubicacion: Optional[str] = None
    estado: str
    creado_en: datetime
    cuenta_actual: float = 0.0

    class Config:
        from_attributes = True


class CobroResponse(BaseModel):
    mesa_numero: int
    total_cobrado: float
    comandas_cerradas: int


# ============ COMANDAS ============

class ComandaPlatoCreate(BaseModel):
    plato_id: int
    cantidad: int = Field(default=1, gt=0, le=99)


class ComandaCreate(BaseModel):
    numero_mesa: int
    platos: List[ComandaPlatoCreate] = Field(..., min_length=1)


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


# ============ MONITOR DE COCINA ============

class MonitorPlatoItem(BaseModel):
    nombre: str
    cantidad: int


class MonitorComandaItem(BaseModel):
    id: int
    numero_mesa: int
    estado: str
    creado_en: datetime
    minutos_transcurridos: int
    platos: List[MonitorPlatoItem]


# ============ COMPRAS ============

class CompraCreate(BaseModel):
    descripcion: str = Field(..., min_length=1, max_length=100)
    categoria: Optional[str] = Field(default=None, max_length=50)
    monto: float = Field(..., gt=0)
    fecha: str  # YYYY-MM-DD


class CompraUpdate(BaseModel):
    descripcion: Optional[str] = Field(default=None, min_length=1, max_length=100)
    categoria: Optional[str] = Field(default=None, max_length=50)
    monto: Optional[float] = Field(default=None, gt=0)
    fecha: Optional[str] = None


class CompraResponse(BaseModel):
    id: int
    cliente_id: str
    descripcion: str
    categoria: Optional[str] = None
    monto: float
    fecha: str
    estado: str
    creado_por: Optional[str] = None
    creado_en: datetime

    class Config:
        from_attributes = True


# ============ DASHBOARD FINANCIERO ============

class DashboardSerieItem(BaseModel):
    fecha: str
    ventas: float
    gastos: float
    ganancia: float
    comandas: int


class DashboardTotales(BaseModel):
    ventas: float
    gastos: float
    ganancia: float
    comandas: int


class TopPlatoItem(BaseModel):
    nombre: str
    cantidad: int
    revenue: float


class DashboardResumen(BaseModel):
    periodo_dias: int
    serie: List[DashboardSerieItem]
    totales: DashboardTotales
    top_platos: List[TopPlatoItem]
