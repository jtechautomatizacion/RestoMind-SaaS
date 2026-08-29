import re

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime


def _validar_celular_peru(valor: str) -> str:
    """Celular peruano: exactamente 9 dígitos, empieza con 9.

    Se limpia de espacios/guiones antes de validar (así "991-056-592" y
    "991 056 592" también pasan), pero lo que se guarda es solo dígitos.
    """
    limpio = re.sub(r"[\s-]", "", valor)
    if not re.fullmatch(r"9\d{8}", limpio):
        raise ValueError("El celular debe tener 9 dígitos y empezar con 9 (ej: 987654321)")
    return limpio


# ============ AUTENTICACIÓN ============

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1, max_length=200)


class UsuarioMe(BaseModel):
    email: str
    nombre: str
    rol: str
    cliente_id: str
    cliente_nombre: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioMe


# ============ SUPERADMIN (panel del revendedor) ============

class SuperAdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1, max_length=200)


class SuperAdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    nombre: str
    email: str


class SuperAdminMe(BaseModel):
    nombre: str
    email: str


class ClienteConStats(BaseModel):
    id: str
    nombre: str
    email: str
    telefono: Optional[str] = None
    pais: str
    estado: str
    creado_en: datetime
    num_usuarios: int
    num_platos: int
    num_mesas: int
    ventas_mes_actual: float


class ClienteCreateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    cliente_id: Optional[str] = Field(default=None, max_length=50)
    email: str = Field(..., min_length=1, max_length=150)
    telefono: Optional[str] = Field(default=None, max_length=30)
    pais: str = Field(default="Perú", max_length=50)
    moneda: str = Field(default="PEN", max_length=10)
    num_mesas: int = Field(default=8, ge=0, le=200)
    admin_nombre: str = Field(..., min_length=1, max_length=100)
    admin_email: str = Field(..., min_length=1, max_length=150)
    admin_password: str = Field(..., min_length=6, max_length=200)

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: Optional[str]) -> Optional[str]:
        # Es opcional: solo se valida el formato si vino algo.
        if not v:
            return v
        return _validar_celular_peru(v)


class ResetPasswordRequest(BaseModel):
    nueva_password: str = Field(..., min_length=6, max_length=200)


class ChangePasswordRequest(BaseModel):
    password_actual: str = Field(..., min_length=1, max_length=200)
    nueva_password: str = Field(..., min_length=6, max_length=200)


class SuperAdminUpdateRequest(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    email: Optional[str] = Field(default=None, min_length=1, max_length=150)


class UsuarioUpdateMeRequest(BaseModel):
    """Solo nombre. Email y rol NO se pueden cambiar."""
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)


# ============ GENÉRICO ============

class EstadoUpdate(BaseModel):
    """Payload genérico para PATCH /.../estado. Cada ruta valida los valores permitidos."""
    estado: str = Field(..., min_length=1)


# ============ CATEGORÍAS ============

class CategoriaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=50)
    icono: str = Field(default="🍽️", min_length=1, max_length=8)


class CategoriaResponse(BaseModel):
    id: int
    cliente_id: str
    nombre: str
    icono: str

    class Config:
        from_attributes = True


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
    imagen_url: Optional[str] = None
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True


# ============ PERSONAL (usuarios de un restaurante) ============

class UsuarioCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)
    rol: str = Field(..., pattern="^(admin|mozo|jefe_cocina|cajero)$")


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    rol: Optional[str] = Field(default=None, pattern="^(admin|mozo|jefe_cocina|cajero)$")
    estado: Optional[str] = Field(default=None, pattern="^(activo|inactivo)$")


class UsuarioResponse(BaseModel):
    id: str
    nombre: str
    email: Optional[str]
    celular: Optional[str]
    rol: str
    estado: str
    creado_en: datetime

    class Config:
        from_attributes = True


class StaffCreateRequest(BaseModel):
    """Crear mozo, cajero o cocinero.

    Ya no se pide celular: el admin normalmente no tiene un número real
    distinto para cada empleado (ni quiere repartir el suyo propio), así
    que el "código de acceso" lo genera el backend — ver crear_staff() en
    routes/usuarios.py. Esto también evita pedir un dato personal (celular
    real) que no hace falta para el login, algo a favor en una auditoría
    de datos.

    El valor de rol para cocina es 'jefe_cocina' — así se llama en toda la
    app (ROLES_PERMITIDOS, dashboard, permisos), no 'cocinero'.
    """
    nombre: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)
    rol: str = Field(..., pattern="^(mozo|cajero|jefe_cocina)$")


class StaffUpdateRequest(BaseModel):
    """Editar staff. Solo nombre y contraseña. No se puede cambiar el código de acceso ni el rol."""
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    password: Optional[str] = Field(default=None, min_length=6, max_length=200)


class LoginStaffRequest(BaseModel):
    """Login para mozo, cajero, cocinero. Usa el código de acceso generado
    al crear la cuenta (ya no es necesariamente un celular real) + contraseña."""
    celular: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=1)


# ============ MESAS ============

class MesaCreate(BaseModel):
    numero: int = Field(..., gt=0)
    capacidad: int = Field(default=4, gt=0, le=50)
    ubicacion: Optional[str] = Field(default=None, max_length=50)


class MesaUpdate(BaseModel):
    numero: Optional[int] = Field(default=None, gt=0)
    capacidad: Optional[int] = Field(default=None, gt=0, le=50)
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
    ingresos: float


class TopGastoItem(BaseModel):
    categoria: str
    cantidad: int
    monto: float


class DashboardResumen(BaseModel):
    periodo_dias: int
    serie: List[DashboardSerieItem]
    totales: DashboardTotales
    top_platos: List[TopPlatoItem]
    top_gastos: List[TopGastoItem]
