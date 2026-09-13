import re

from pydantic import BaseModel, Field, PlainSerializer, field_validator, model_validator
from typing import Annotated, List, Literal, Optional
from datetime import date, datetime, timezone

from backend.utils.padron import digito_verificador_ok
from backend.utils.roles import ROLES_STAFF, roles_de


def _a_iso_utc(valor: datetime) -> str:
    """Serializa un timestamp con la marca 'Z' explícita de UTC.

    Toda la app guarda instantes con datetime.utcnow(): naive, pero en UTC.
    Sin la marca, la API emitía '2026-09-01T06:36:27' y el navegador
    interpreta un ISO sin zona como hora LOCAL (así lo manda el estándar),
    de modo que mostraba las 06:36 UTC como si ya fueran las 06:36 de Lima
    — cinco horas de más en cada fecha visible de la app. Ni el backend ni
    los tests lo veían, porque el dato viajaba bien: lo único ambiguo era
    cómo había que leerlo.

    Se corrige acá y no en cada `new Date()` del frontend porque el contrato
    de la API es el lugar correcto: cualquier cliente futuro (otra app, una
    integración) hereda el arreglo sin repetir el mismo truco.
    """
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# Para INSTANTES (cuándo ocurrió algo, en la línea de tiempo real).
#
# NO usar en fechas de CALENDARIO del negocio — como MovimientoResponse.fecha,
# que es "el día al que corresponde esta merma" y el admin puede fecharla
# ayer. Esas se guardan a medianoche naive; marcarlas como UTC las correría
# un día hacia atrás en cualquier zona al oeste de Greenwich (en Lima, el
# 01/09 a las 00:00 pasaría a mostrarse como 31/08).
UtcDatetime = Annotated[datetime, PlainSerializer(_a_iso_utc, return_type=str, when_used="json")]


def _validar_roles_staff(roles: List[str]) -> List[str]:
    """Compartido entre StaffCreateRequest y StaffUpdateRequest: sin roles
    vacío no tiene sentido (una cuenta sin ningún permiso), 'admin' nunca
    puede colarse por acá (ese lo asigna el superadmin al crear el
    restaurante, ver crear_usuario en routes/usuarios.py), y duplicados son
    un error del cliente, no algo a tolerar en silencio."""
    if not roles:
        raise ValueError("Debe seleccionar al menos un rol")
    if len(set(roles)) != len(roles):
        raise ValueError("No repitas el mismo rol")
    invalidos = [r for r in roles if r not in ROLES_STAFF]
    if invalidos:
        raise ValueError(f"Rol inválido: {invalidos[0]}")
    return roles


def _validar_celular_peru(valor: str) -> str:
    """Celular peruano: exactamente 9 dígitos, empieza con 9.

    Se limpia de espacios/guiones antes de validar (así "991-056-592" y
    "991 056 592" también pasan), pero lo que se guarda es solo dígitos.
    """
    limpio = re.sub(r"[\s-]", "", valor)
    if not re.fullmatch(r"9\d{8}", limpio):
        raise ValueError("El celular debe tener 9 dígitos y empezar con 9 (ej: 987654321)")
    return limpio


def _validar_email(valor: str) -> str:
    """Formato de email razonable, en minúsculas y sin espacios alrededor.

    No pretende cubrir todo el RFC 5322 (que admite rarezas que ningún
    proveedor real acepta): busca atajar el caso que de verdad pasa, un
    email mal tipeado al dar de alta un restaurante. Sin esta validación,
    `admin_email` era un str suelto y cualquier cosa llegaba hasta el envío
    SMTP; un destinatario inválido rebota, y una tasa alta de rebotes es de
    las señales que usa Google para limitar la cuenta que envía.

    Ojo: que el formato sea válido no garantiza que el dominio exista
    (buensabor.pe pasa este filtro y no existe). Para eso haría falta una
    consulta DNS de MX, que hoy no se hace — en desarrollo se evita el
    problema no enviando nada (ver backend/email.py).
    """
    limpio = valor.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+", limpio):
        raise ValueError("Email inválido (ej: nombre@dominio.com)")
    return limpio


def _validar_ruc_peru(valor: str) -> str:
    """
    RUC peruano: 11 dígitos, prefijo en uso y dígito verificador correcto.

    Antes se aceptaban SOLO los prefijos 10 y 20. Estaba mal: SUNAT también
    usa 15, 16 y 17 para personas naturales (asignaciones antiguas). Sobre
    una muestra de 154.132 contribuyentes reales del Padrón Reducido,
    11.432 —el 7,4%— empezaban en 15 o 17, y a todos ellos esta validación
    les rechazaba el RUC al pedir factura.

    Se agregó además el DÍGITO VERIFICADOR, que es lo que de verdad separa
    "once dígitos cualesquiera" de "un RUC que puede existir": atrapa el
    número mal tipeado en el mostrador sin consultar nada. Verificado contra
    esos mismos 154.132 RUC reales, con 100% de coincidencia.
    """
    limpio = re.sub(r"[\s-]", "", valor)
    if not re.fullmatch(r"(10|15|16|17|20)\d{9}", limpio):
        raise ValueError(
            "El RUC debe tener 11 dígitos y empezar con 10, 15, 16, 17 o 20 (ej: 10200812234)"
        )
    if not digito_verificador_ok(limpio):
        raise ValueError("Ese RUC no existe: revisa que los 11 dígitos estén bien copiados")
    return limpio


# ============ AUTENTICACIÓN ============

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1, max_length=200)


class UsuarioMe(BaseModel):
    email: str
    nombre: str
    rol: str
    # Ver UsuarioResponse.roles — misma idea, pero acá se pasa explícito en
    # cada construcción (routes/auth.py) porque UsuarioMe no siempre sale de
    # un objeto Usuario del ORM (el login de superadmin no tiene fila en
    # esa tabla).
    roles: List[str]
    cliente_id: str
    cliente_nombre: str
    # Datos del negocio para imprimir tickets/pre-cuentas sin una llamada
    # aparte (ver frontend/js/print.js) — el mozo los tiene disponibles
    # desde que abre sesión, igual que cliente_nombre ya funcionaba.
    cliente_ruc: Optional[str] = None
    # El frontend lo usa para NO intentar emitir boleta en un restaurante
    # que no factura desde acá — sin esto le salía un toast rojo en cada
    # cobro (ver generarBoletaTrasCobro en frontend/js/mozo.js).
    cliente_usar_sunat: bool = False
    # ¿Este restaurante puede emitir FACTURAS o solo boletas? Lo necesita el
    # MOZO al cobrar, para mostrar qué comprobante va a salir ANTES de
    # confirmar — y un mozo no puede consultar /configuracion, que es
    # admin-only. Por eso viaja en la sesión, igual que cliente_usar_sunat.
    cliente_emite_facturas: bool = False
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
    timestamp: UtcDatetime
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
    emite_facturas: bool = False
    direccion: Optional[str] = None
    pais: str
    estado: str
    creado_en: UtcDatetime
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
    # ¿Este restaurante puede emitir FACTURAS o solo boletas? Lo decide su
    # RÉGIMEN TRIBUTARIO, no una preferencia: un contribuyente del Nuevo RUS
    # tiene prohibido facturar. Default False porque es el caso seguro —
    # emitir boletas de más nunca es infracción; facturar sin poder, sí.
    # Solo el superadmin lo activa, tras confirmar el régimen del cliente.
    emite_facturas: bool = False

    direccion: Optional[str] = Field(default=None, max_length=200)
    pais: str = Field(default="Perú", max_length=50)
    moneda: str = Field(default="PEN", max_length=10)
    num_mesas: int = Field(default=8, ge=0, le=200)
    admin_nombre: str = Field(..., min_length=1, max_length=100)
    admin_email: str = Field(..., min_length=1, max_length=150)
    admin_password: str = Field(..., min_length=6, max_length=200)

    @field_validator("email", "admin_email")
    @classmethod
    def validar_emails(cls, v: str) -> str:
        return _validar_email(v)

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
    # Ver ClienteCreateRequest.emite_facturas: lo decide el RÉGIMEN
    # TRIBUTARIO del cliente (el Nuevo RUS no puede facturar), no una
    # preferencia. Solo el superadmin lo cambia.
    emite_facturas: bool = False
    direccion: Optional[str] = Field(default=None, max_length=200)
    pais: str = Field(default="Perú", max_length=50)
    moneda: str = Field(default="PEN", max_length=10)
    admin_nombre: str = Field(..., min_length=1, max_length=100)
    admin_email: str = Field(..., min_length=1, max_length=150)
    admin_password: Optional[str] = Field(default=None, max_length=200)

    @field_validator("email", "admin_email")
    @classmethod
    def validar_emails(cls, v: str) -> str:
        return _validar_email(v)

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
    creado_en: UtcDatetime

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
    # 'rol' se mantiene tal cual (valor único) SOLO para los guards de
    # admin en routes/usuarios.py (bloquear que alguien intente ascender a
    # "admin", o que un admin se quite su propio rol) — la UI ya no lo usa
    # para editar personal. 'roles' (lista) es el camino real para eso: una
    # cuenta de staff puede cubrir varias tareas a la vez (ej. cocina Y
    # caja), ver backend/utils/roles.py.
    rol: Optional[str] = Field(default=None, pattern="^(admin|mozo|jefe_cocina|cajero)$")
    roles: Optional[List[str]] = Field(default=None, min_length=1)
    estado: Optional[str] = Field(default=None, pattern="^(activo|inactivo)$")

    @field_validator("roles")
    @classmethod
    def _validar_roles(cls, v):
        return _validar_roles_staff(v) if v is not None else v


class UsuarioResponse(BaseModel):
    id: str
    nombre: str
    email: Optional[str]
    celular: Optional[str]
    rol: str
    # Una cuenta de staff puede cubrir varias tareas a la vez (ej. cocina Y
    # caja, cuando el restaurante tiene poco personal) — `rol` en BD guarda
    # esa combinación como CSV (ver backend/utils/roles.py); `roles` es esa
    # lista ya separada, lo que consume el frontend. `admin` sigue siendo
    # un solo valor exclusivo, nunca combinado: acá se ve como ['admin'].
    roles: List[str] = Field(default_factory=list)
    estado: str
    creado_en: UtcDatetime

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def _derivar_roles(self):
        # 'roles' nunca viene del ORM (no es una columna) — se deriva
        # siempre del 'rol' real de la fila. Se usa "after" (no un
        # field_validator con default) porque un validador con default
        # nunca se ejecuta si el campo no vino en el input, y acá nunca
        # viene: from_attributes=True lee 'rol' directo del objeto ORM.
        self.roles = ["admin"] if self.rol == "admin" else roles_de(self.rol)
        return self


class StaffCreateRequest(BaseModel):
    """Crear una cuenta de personal (mozo/cajero/cocina), con uno o varios
    roles a la vez.

    Ya no se pide celular: el admin normalmente no tiene un número real
    distinto para cada empleado (ni quiere repartir el suyo propio), así
    que el "código de acceso" lo genera el backend — ver crear_staff() en
    routes/usuarios.py. Esto también evita pedir un dato personal (celular
    real) que no hace falta para el login, algo a favor en una auditoría
    de datos.

    `roles` es una lista (no un solo string) porque en restaurantes con
    poco personal una sola persona suele cubrir más de una tarea (ej.
    cocina Y caja) — ver backend/utils/roles.py. El valor para cocina es
    'jefe_cocina' — así se llama en toda la app (ROLES_PERMITIDOS,
    dashboard, permisos), no 'cocinero'. 'admin' nunca es una opción acá.
    """
    nombre: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)
    roles: List[str] = Field(..., min_length=1)

    @field_validator("roles")
    @classmethod
    def _validar(cls, v):
        return _validar_roles_staff(v)


class StaffUpdateRequest(BaseModel):
    """Editar staff: nombre, contraseña y/o roles. El código de acceso NO
    se puede cambiar (cambiarlo sería re-crear la cuenta)."""
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    password: Optional[str] = Field(default=None, min_length=6, max_length=200)
    roles: Optional[List[str]] = Field(default=None, min_length=1)

    @field_validator("roles")
    @classmethod
    def _validar(cls, v):
        return _validar_roles_staff(v) if v is not None else v


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
    creado_en: UtcDatetime
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
    creado_en: UtcDatetime

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
    creado_en: UtcDatetime
    minutos_transcurridos: int
    platos: List[MonitorPlatoItem]


# ============ COMPRAS ============

class CompraCreate(BaseModel):
    descripcion: str = Field(..., min_length=1, max_length=100)
    categoria: Optional[str] = Field(default=None, max_length=50)
    monto: float = Field(..., gt=0)
    fecha: str  # YYYY-MM-DD


class CompraUpdate(BaseModel):
    # monto NO es editable a propósito: cambiar el monto de un gasto ya
    # registrado rompería la trazabilidad de caja/dashboard para ese día.
    # Si el monto está mal, se cancela el gasto y se crea uno nuevo.
    descripcion: Optional[str] = Field(default=None, min_length=1, max_length=100)
    categoria: Optional[str] = Field(default=None, max_length=50)
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
    creado_en: UtcDatetime

    class Config:
        from_attributes = True


# ============ INVENTARIO (INSUMOS) ============

# Lista cerrada a propósito: con texto libre, "kg", "Kg", "kilos" y "kilo"
# terminan siendo cuatro unidades distintas para lo mismo — el mismo
# problema que ya tuvo la carta antes de que las categorías fueran un
# catálogo propio (ver backend/routes/categorias.py).
UNIDADES_VALIDAS = ("kg", "gramo", "litro", "ml", "unidad", "docena", "paquete", "caja")


class InsumoCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=60)
    unidad: str = Field(..., min_length=1, max_length=20)
    # cantidad_actual admite 0 (se acabó, pero el insumo sigue en la lista);
    # cantidad_minima no, porque un mínimo de 0 nunca dispararía una alerta
    # y volvería inútil la fila.
    cantidad_actual: float = Field(..., ge=0)
    cantidad_minima: float = Field(..., gt=0)

    @field_validator("unidad")
    @classmethod
    def validar_unidad(cls, v: str) -> str:
        unidad = v.strip().lower()
        if unidad not in UNIDADES_VALIDAS:
            raise ValueError(f"Unidad inválida. Use una de: {', '.join(UNIDADES_VALIDAS)}")
        return unidad


class InsumoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=60)
    unidad: Optional[str] = Field(default=None, min_length=1, max_length=20)
    cantidad_actual: Optional[float] = Field(default=None, ge=0)
    cantidad_minima: Optional[float] = Field(default=None, gt=0)

    @field_validator("unidad")
    @classmethod
    def validar_unidad(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        unidad = v.strip().lower()
        if unidad not in UNIDADES_VALIDAS:
            raise ValueError(f"Unidad inválida. Use una de: {', '.join(UNIDADES_VALIDAS)}")
        return unidad


class InsumoResponse(BaseModel):
    id: int
    cliente_id: str
    nombre: str
    unidad: str
    cantidad_actual: float
    cantidad_minima: float
    # Derivado, no una columna: guardarlo en la BD obligaría a recalcular la
    # fila entera cada vez que cambia el mínimo o la cantidad, con el riesgo
    # de que quede desincronizado. Se calcula al responder (ver routes/insumos.py).
    estado: str  # "ok" | "bajo" | "critico"
    creado_en: UtcDatetime

    class Config:
        from_attributes = True


# Razones válidas de un movimiento de stock. Lista cerrada por el mismo
# motivo que UNIDADES_VALIDAS: con texto libre, "merma"/"Merma"/"se echó a
# perder" terminan siendo tres categorías para lo mismo y el historial deja
# de servir para responder "¿en qué se me va el pescado?".
# "reversion" no se ofrece en el POST — la pone el sistema al deshacer.
RAZONES_VALIDAS = ("compra", "uso", "ajuste", "merma", "otro")


class MovimientoCreate(BaseModel):
    tipo: Literal["entrada", "salida"]
    cantidad: float = Field(..., gt=0)  # Siempre positiva: el signo lo da 'tipo'
    razon: str = Field(default="otro", max_length=20)
    # Fecha de negocio. Opcional: si no viene, es hoy — el caso normal es
    # anotar el movimiento en el momento.
    fecha: Optional[date] = None

    @field_validator("razon")
    @classmethod
    def validar_razon(cls, v: str) -> str:
        razon = v.strip().lower()
        if razon not in RAZONES_VALIDAS:
            raise ValueError(f"Razón inválida. Use una de: {', '.join(RAZONES_VALIDAS)}")
        return razon

    @field_validator("fecha")
    @classmethod
    def validar_fecha(cls, v: Optional[date]) -> Optional[date]:
        # Mismo criterio que Compra: se puede registrar algo de ayer, nunca
        # de mañana. Un movimiento futuro descuadraría el stock de hoy.
        if v is not None and v > date.today():
            raise ValueError("La fecha no puede ser futura")
        return v


class MovimientoResponse(BaseModel):
    id: int
    insumo_id: int
    tipo: str
    cantidad: float
    razon: str
    saldo_despues: float
    fecha: datetime
    usuario_nombre: Optional[str] = None
    creado_en: UtcDatetime
    # El frontend lo usa para tachar la fila y esconder su botón de deshacer.
    revertido: bool = False

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
    # Opcional: sin esto, el historial solo distingue turnos por hora
    # ("Turno 2 de hoy"). Con un restaurante que abre mañana/tarde/noche,
    # una etiqueta es más rápida de leer que calcular mentalmente a qué
    # hora empezó cada uno.
    nombre_turno: Optional[str] = Field(default=None, max_length=50)

    @field_validator("nombre_turno")
    @classmethod
    def _vacio_a_none(cls, v):
        v = (v or "").strip()
        return v or None


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
    abierto_en: UtcDatetime
    abierto_por: str
    nombre_turno: Optional[str] = None

    ventas_cobradas: Optional[float] = None
    gastos_efectivo: Optional[float] = None
    retiros_personales: Optional[float] = None

    saldo_esperado: Optional[float] = None
    saldo_contado: Optional[float] = None
    diferencia: Optional[float] = None
    variacion_pct: Optional[float] = None
    razon_discrepancia: Optional[str] = None

    cerrado_en: Optional[UtcDatetime] = None
    cerrado_por: Optional[str] = None
    estado: str

    class Config:
        from_attributes = True


class PushTokenRequest(BaseModel):
    """Token FCM que el navegador entrega tras pedir permiso de
    notificaciones (ver frontend/js/push-notifications.js)."""
    token: str = Field(..., min_length=10, max_length=500)


class PushDesregistrarRequest(BaseModel):
    """Baja de un dispositivo. `token` es opcional a propósito: sin él se dan
    de baja TODOS los del usuario — el caso del navegador que perdió su
    localStorage y ya no sabe qué token borrar (ver routes/push.py)."""
    token: Optional[str] = Field(default=None, min_length=10, max_length=500)


class PushEstadoResponse(BaseModel):
    activo: bool


class CajaGateResponse(BaseModel):
    """Semáforo minimal para Mesas/Cocina — a propósito no lleva montos ni
    ningún otro dato financiero, porque cualquier rol (mozo, cocina) puede
    consultarlo sin ser admin (ver GET /caja/gate)."""
    hay_caja_abierta: bool


class CajaEstadoResponse(BaseModel):
    """
    Snapshot en vivo para pintar la pantalla de Caja sin que el admin tenga
    que adivinar en qué paso del flujo está. Solo puede haber UN turno
    abierto a la vez (lo impone POST /caja/abrir) — por eso `caja_abierta`
    no necesariamente es de hoy: si el admin se olvidó de cerrar ayer, sigue
    siendo el turno abierto hasta que lo cierre (`es_atrasada=True` avisa al
    frontend). Un restaurante puede tener varios turnos el mismo día
    (mañana/tarde) — `turnos_hoy` cuenta cuántos hubo hoy en total, y
    `ultimo_cierre_hoy` es solo el más reciente cerrado (el historial
    completo lista todos). Abrir un turno nuevo NUNCA depende de si ya
    hubo uno cerrado hoy — solo de que no haya uno abierto en este momento.
    ventas_hasta_ahora/gastos_hasta_ahora se recalculan en cada consulta
    mientras el turno sigue abierto — a diferencia de los mismos campos en
    `caja_abierta.ventas_cobradas` etc., que se congelan recién al cerrar.
    """
    hay_caja_abierta: bool
    caja_abierta: Optional[CierreCajaResponse] = None
    es_atrasada: bool = False
    ventas_hasta_ahora: float = 0
    gastos_hasta_ahora: float = 0
    ultimo_cierre_hoy: Optional[CierreCajaResponse] = None
    turnos_hoy: int = 0


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

    # Salida de emergencia para el caso "RUC que el padrón local todavía no
    # tiene" (uno recién inscrito, o la copia local sin actualizar).
    #
    # SUNAT no acepta una factura sin razón social, así que sin esto la venta
    # se quedaría sin comprobante hasta que alguien recargue 1,6 GB de
    # padrón. Con esto, el cajero lo escribe a mano y la factura sale.
    #
    # Solo se usa cuando el documento es un RUC: en una boleta el nombre no
    # hace falta, y aceptarlo ahí abriría la puerta a emitir a nombre de
    # cualquiera sin ningún respaldo.
    razon_social_manual: Optional[str] = Field(default=None, max_length=200)

    @field_validator("razon_social_manual")
    @classmethod
    def limpiar_razon_social_manual(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        limpio = " ".join(v.split())
        return limpio or None

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
    creado_en: UtcDatetime
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
    creado_en: UtcDatetime


class FacturaPendienteItem(BaseModel):
    """Factura que ya reservó su correlativo pero no llegó a emitirse.
    Se arregla reintentando (POST /facturas/{id}/reintentar)."""
    id: int
    numero_boleta: str
    numero_mesa: int
    total: float
    estado: str
    error_mensaje: Optional[str] = None
    creado_en: UtcDatetime


class VentaSinBoletaItem(BaseModel):
    """Comandas cobradas que nunca llegaron a tener Factura (la petición no
    alcanzó el servidor). Se arregla emitiendo de cero con
    POST /facturas/generar sobre esos comanda_ids."""
    numero_mesa: int
    comanda_ids: List[int]
    total: float
    creado_en: UtcDatetime


class FacturasPendientesResponse(BaseModel):
    facturas_con_error: List[FacturaPendienteItem]
    ventas_sin_boleta: List[VentaSinBoletaItem]


# ============ AGENTE DE DESCARGA (PC del restaurante) ============

class ComprobanteParaDescargar(BaseModel):
    """Un comprobante listo para que el agente lo deposite en la carpeta
    del Facturador SUNAT.

    Los cuatro archivos viajan JUNTOS, en el mismo objeto, y no en cuatro
    descargas separadas: el Facturador necesita los cuatro para procesar la
    boleta, y bajarlos de a uno abre la ventana para que una caída de red
    deje un comprobante incompleto en la carpeta. Pesan menos de 1 KB en
    total, así que no hay razón para separarlos.
    """
    id: int
    nombre_base: str  # RUC-tipo-serie-correlativo, sin extensión
    numero_boleta: str
    cab: str
    det: str
    tri: str
    ley: str


class AgentePendientesResponse(BaseModel):
    comprobantes: List[ComprobanteParaDescargar]


class AgenteConfirmarRequest(BaseModel):
    ids: List[int] = Field(..., min_length=1)


class AgentePingResponse(BaseModel):
    """Para que el instalador valide el token sin bajar comprobantes."""
    cliente_id: str
    cliente_nombre: str
    pendientes: int


# ============ CONFIGURACIÓN DEL RESTAURANTE (admin) ============

class ConfiguracionUpdateRequest(BaseModel):
    usar_sunat: bool


class ConfiguracionResponse(BaseModel):
    usar_sunat: bool
    # El frontend lo usa para explicar POR QUÉ el interruptor está
    # deshabilitado, en vez de dejarlo muerto sin decir nada.
    tiene_ruc: bool
    ruc: Optional[str] = None
    razon_social: Optional[str] = None
    # Se llama direccion_fiscal de cara al frontend, pero la columna es
    # Cliente.direccion — es el domicilio que va en el encabezado de los
    # comprobantes, o sea el fiscal. No se renombró la columna para no
    # forzar una migración por un tema de vocabulario.
    direccion_fiscal: Optional[str] = None
    # Con la facturación activa, el RUC/razón social quedan congelados: el
    # certificado está emitido A NOMBRE de ese RUC. El frontend usa esto para
    # mostrarlos de solo lectura en vez de ofrecer campos que el backend va
    # a rechazar.
    datos_fiscales_bloqueados: bool = False
    # ¿Este restaurante puede emitir facturas, o solo boletas? En Nuevo RUS
    # es False y un comensal con RUC igual recibe boleta.
    emite_facturas: bool = False
    # True solo para el tenant de pruebas (RUC 20000000001). El frontend lo
    # usa para precargar las credenciales públicas de BETA y avisar que nada
    # de lo que se emita ahí tiene efecto tributario.
    es_ambiente_beta: bool = False


# ============ CONSULTA DE RUC (Padrón Reducido SUNAT) ============

class RucConsultaResponse(BaseModel):
    """
    Resultado de buscar un RUC en la copia local del padrón.

    `encontrado=False` NO es un error: significa que ese RUC no figura en el
    padrón descargado (puede ser reciente, o el archivo local estar viejo).
    El cajero igual puede emitir escribiendo el nombre a mano.
    """
    ruc: str
    encontrado: bool
    nombre: Optional[str] = None
    estado: Optional[str] = None       # ACTIVO, BAJA DE OFICIO...
    condicion: Optional[str] = None    # HABIDO, NO HABIDO...
    # RUC 10/15/16/17 son personas naturales: el "nombre" es el de una
    # persona real. El frontend lo usa para no rotular ese dato como
    # "razón social" cuando en realidad es el nombre de alguien.
    persona_natural: Optional[bool] = None
    puede_facturarse: Optional[bool] = None
    advertencia: Optional[str] = None


class RucPadronEstadoResponse(BaseModel):
    disponible: bool
    contribuyentes: int = 0
    # Fecha del archivo local. SUNAT publica el padrón a diario, así que
    # sirve para saber si conviene volver a cargarlo.
    actualizado_en: Optional[str] = None


class DocumentoConsultaResponse(BaseModel):
    """
    Resultado de consultar un documento de comprador (DNI o RUC).

    `encontrado=False` NO es un error: puede ser un RUC recién inscrito, una
    copia del padrón sin actualizar, o un DNI que este restaurante todavía
    no atendió. El cajero escribe el nombre a mano y sigue cobrando —
    `requiere_nombre_manual` es lo que le dice al frontend que despliegue
    ese campo en vez de mostrar un error.
    """
    documento: str
    tipo: Literal["DNI", "RUC"]
    encontrado: bool
    nombre: Optional[str] = None
    # "local" = ya estaba guardado en este restaurante; "api" = lo trajo el
    # servicio externo; "manual" = lo escribió el cajero. Solo aplica a DNI.
    origen: Optional[str] = None
    persona_natural: Optional[bool] = None
    puede_facturarse: Optional[bool] = None
    requiere_nombre_manual: bool = False
    advertencia: Optional[str] = None


class DocumentoGuardarRequest(BaseModel):
    """El nombre que el cajero escribió a mano, para no tener que volver a
    tipearlo la próxima vez que venga esa persona."""
    nombre: str = Field(..., min_length=1, max_length=200)
