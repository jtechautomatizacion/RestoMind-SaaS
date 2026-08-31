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


def _validar_ruc_peru(valor: str) -> str:
    """RUC peruano: exactamente 11 dígitos, empieza con 10 (persona natural
    con negocio) o 20 (persona jurídica) — los únicos dos prefijos que
    SUNAT usa para contribuyentes que emiten boletas de venta.
    """
    limpio = re.sub(r"[\s-]", "", valor)
    if not re.fullmatch(r"(10|20)\d{9}", limpio):
        raise ValueError("El RUC debe tener 11 dígitos y empezar con 10 o 20 (ej: 10200812234)")
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
    # Datos del negocio para imprimir tickets/pre-cuentas sin una llamada
    # aparte (ver frontend/js/print.js) — el mozo los tiene disponibles
    # desde que abre sesión, igual que cliente_nombre ya funcionaba.
    cliente_ruc: Optional[str] = None
    cliente_razon_social: Optional[str] = None
    cliente_direccion: Optional[str] = None
    cliente_email: Optional[str] = None


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


class AuditLogResponse(BaseModel):
    id: int
    timestamp: datetime
    actor: str
    accion: str
    entidad: str
    entidad_id: str
    cliente_id: Optional[str]
    detalle: Optional[str]

    class Config:
        from_attributes = True


class ClienteConStats(BaseModel):
    id: str
    nombre: str
    email: str
    telefono: Optional[str] = None
    ruc: Optional[str] = None
    razon_social: Optional[str] = None
    direccion: Optional[str] = None
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
    ruc: Optional[str] = Field(default=None, max_length=15)
    razon_social: Optional[str] = Field(default=None, max_length=150)
    direccion: Optional[str] = Field(default=None, max_length=200)
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

    @field_validator("ruc")
    @classmethod
    def validar_ruc(cls, v: Optional[str]) -> Optional[str]:
        # Opcional a propósito: un restaurante puede darse de alta y
        # configurar SUNAT después. Sin RUC, /api/facturas/generar rechaza
        # con un 400 claro en vez de fallar a mitad de una emisión.
        if not v:
            return v
        return _validar_ruc_peru(v)


class ClienteUpdateRequest(BaseModel):
    """
    Igual que ClienteCreateRequest, salvo admin_password: ahí SIEMPRE hace
    falta una contraseña inicial, acá NO — el formulario de edición invita
    a "dejar en blanco si no deseas cambiar", y backend/routes/superadmin.py
    ya está escrito para tratarla como opcional (`if payload.admin_password`).

    Antes de que existiera este schema, editar_cliente() usaba
    ClienteCreateRequest para las dos cosas: el campo vacío que mandaba el
    frontend (comportamiento esperado del formulario) chocaba con
    min_length=6 de ese schema, y la edición fallaba con 422 el 100% de las
    veces que no se tocaba la contraseña — justo el caso más común.
    """
    nombre: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=1, max_length=150)
    telefono: Optional[str] = Field(default=None, max_length=30)
    ruc: Optional[str] = Field(default=None, max_length=15)
    razon_social: Optional[str] = Field(default=None, max_length=150)
    direccion: Optional[str] = Field(default=None, max_length=200)
    pais: str = Field(default="Perú", max_length=50)
    moneda: str = Field(default="PEN", max_length=10)
    admin_nombre: str = Field(..., min_length=1, max_length=100)
    admin_email: str = Field(..., min_length=1, max_length=150)
    admin_password: Optional[str] = Field(default=None, max_length=200)

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        return _validar_celular_peru(v)

    @field_validator("ruc")
    @classmethod
    def validar_ruc(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        return _validar_ruc_peru(v)

    @field_validator("admin_password")
    @classmethod
    def validar_admin_password(cls, v: Optional[str]) -> Optional[str]:
        # "" (input vacío del form) se normaliza a None ANTES de que el
        # handler pregunte `if payload.admin_password` — así una cadena vacía
        # y "no mandar el campo" terminan significando exactamente lo mismo:
        # no cambiar la contraseña. Si SÍ viene algo, tiene que cumplir el
        # mismo mínimo que al crear la cuenta, no una contraseña de 1 char.
        if not v:
            return None
        if len(v) < 6:
            raise ValueError("La nueva contraseña debe tener al menos 6 caracteres")
        return v


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
    comanda_ids: List[int] = Field(default_factory=list)


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


# ============ CAJA (Apertura/Cierre) ============

class AbrirCajaRequest(BaseModel):
    saldo_inicial: float = Field(..., ge=0, le=100000)


class CerrarCajaRequest(BaseModel):
    saldo_contado: float = Field(..., ge=0, le=100000)
    retiros_personales: float = Field(default=0, ge=0, le=100000)
    razon_discrepancia: Optional[str] = Field(default=None, max_length=300)

    @field_validator("razon_discrepancia")
    @classmethod
    def _vacio_a_none(cls, v):
        v = (v or "").strip()
        return v or None


class CierreCajaResponse(BaseModel):
    id: int
    fecha: str
    saldo_inicial: float
    abierto_en: datetime
    abierto_por: str

    ventas_cobradas: Optional[float] = None
    gastos_efectivo: Optional[float] = None
    retiros_personales: Optional[float] = None

    saldo_esperado: Optional[float] = None
    saldo_contado: Optional[float] = None
    diferencia: Optional[float] = None
    variacion_pct: Optional[float] = None
    razon_discrepancia: Optional[str] = None

    cerrado_en: Optional[datetime] = None
    cerrado_por: Optional[str] = None
    estado: str

    class Config:
        from_attributes = True


class CajaGateResponse(BaseModel):
    """Semáforo minimal para Mesas/Cocina — a propósito no lleva montos ni
    ningún otro dato financiero, porque cualquier rol (mozo, cocina) puede
    consultarlo sin ser admin (ver GET /caja/gate)."""
    hay_caja_abierta: bool


class CajaEstadoResponse(BaseModel):
    """
    Snapshot en vivo para pintar la pantalla de Caja sin que el admin tenga
    que adivinar en qué paso del flujo está. Solo puede haber UNA caja
    abierta a la vez (lo impone POST /caja/abrir) — por eso `caja_abierta`
    no necesariamente es la de hoy: si el admin se olvidó de cerrar ayer,
    sigue siendo la caja abierta hasta que la cierre (`es_atrasada=True`
    avisa al frontend para mostrar ese caso distinto del flujo normal).
    ventas_hasta_ahora/gastos_hasta_ahora se recalculan en cada consulta
    mientras la caja sigue abierta — a diferencia de los mismos campos en
    `caja_abierta.ventas_cobradas` etc., que se congelan recién al cerrar.
    """
    hay_caja_abierta: bool
    caja_abierta: Optional[CierreCajaResponse] = None
    es_atrasada: bool = False
    ventas_hasta_ahora: float = 0
    gastos_hasta_ahora: float = 0
    caja_cerrada_hoy: Optional[CierreCajaResponse] = None


# ============ FACTURACIÓN SUNAT ============

class FacturaGenerarRequest(BaseModel):
    """
    Genera una boleta a partir de comandas YA cobradas (no de una lista de
    platos que mande el frontend). El detalle de la boleta se arma en el
    servidor leyendo ComandaPlato de esas comandas — así nadie puede pedir
    una boleta por algo distinto de lo que el sistema registró como vendido.
    """
    comanda_ids: List[int] = Field(..., min_length=1)

    # Un solo campo crudo, tal como lo tipea el cajero — el backend decide
    # tipo de documento/nombre a partir de su longitud (ver
    # routes/facturas.py:_resolver_comprador). Deliberadamente NO se le pide
    # al frontend que mande tipo_documento ya resuelto: esa regla vive en un
    # solo lugar (el servidor), para que nunca pueda divergir entre lo que
    # decide el JS y lo que termina en el archivo SUNAT.
    documento_comprador: Optional[str] = Field(default=None, max_length=15)

    @field_validator("documento_comprador")
    @classmethod
    def validar_documento_comprador(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        limpio = re.sub(r"[\s-]", "", v)
        if not limpio:
            return None
        if len(limpio) == 8 and limpio.isdigit():
            return limpio
        if len(limpio) == 11:
            # Mismo criterio que el RUC del emisor (_validar_ruc_peru): 11
            # dígitos empezando en 10 o 20. Antes bastaba con "11 dígitos",
            # así que un tipeo como 11111111111 pasaba como RUC válido y
            # SUNAT recién lo rechazaba con el comprobante ya emitido.
            return _validar_ruc_peru(limpio)
        raise ValueError(
            "El documento del cliente debe estar vacío, tener 8 dígitos (DNI) "
            "u 11 dígitos empezando en 10 o 20 (RUC)"
        )


class FacturaDetalleItem(BaseModel):
    descripcion: str
    cantidad: int
    precio_unitario: float
    subtotal: float


class FacturaResponse(BaseModel):
    id: int
    numero_mesa: int
    serie: str
    numero_correlativo: int
    numero_boleta: str  # "B001-00000001", calculado, no columna de BD
    subtotal: float
    igv: float
    total: float
    pdf_url: Optional[str] = None
    qr_code: Optional[str] = None
    archivo_local: Optional[str] = None
    estado: str
    error_mensaje: Optional[str] = None
    creado_en: datetime
    fecha_emision_local: Optional[str] = None
    hora_emision_local: Optional[str] = None

    # Datos que el frontend necesita para IMPRIMIR el ticket sin pedirlos
    # aparte (ver frontend/js/print.js) — el emisor sale de Cliente, no de
    # la propia Factura, así que se completan al armar la respuesta.
    ruc_emisor: str
    razon_social_emisor: str
    nombre_emisor: str
    direccion_emisor: Optional[str] = None
    email_emisor: Optional[str] = None
    tipo_documento_comprador: str
    numero_documento_comprador: str
    nombre_comprador: str
    detalles: List["FacturaDetalleItem"] = Field(default_factory=list)


class FacturaListItem(BaseModel):
    id: int
    numero_mesa: int
    numero_boleta: str
    total: float
    estado: str
    creado_en: datetime


class FacturaPendienteItem(BaseModel):
    """Factura que ya reservó su correlativo pero no llegó a emitirse.
    Se arregla reintentando (POST /facturas/{id}/reintentar)."""
    id: int
    numero_boleta: str
    numero_mesa: int
    total: float
    estado: str
    error_mensaje: Optional[str] = None
    creado_en: datetime


class VentaSinBoletaItem(BaseModel):
    """Comandas cobradas que nunca llegaron a tener Factura (la petición no
    alcanzó el servidor). Se arregla emitiendo de cero con
    POST /facturas/generar sobre esos comanda_ids."""
    numero_mesa: int
    comanda_ids: List[int]
    total: float
    creado_en: datetime


class FacturasPendientesResponse(BaseModel):
    facturas_con_error: List[FacturaPendienteItem]
    ventas_sin_boleta: List[VentaSinBoletaItem]
