from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class SuperAdmin(Base):
    """
    Cuenta del dueño del sistema (el revendedor), no de un restaurante.
    Deliberadamente sin cliente_id: no pertenece a ningún tenant, ve todos.
    Separada de Usuario (no solo un Usuario con cliente_id nulo) para que
    sea imposible confundir un token de restaurante con uno de superadmin
    por un descuido de validación — son dos tablas, dos flujos de login,
    dos tipos de token.
    """
    __tablename__ = "superadmins"

    id = Column(String, primary_key=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(String, primary_key=True)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    telefono = Column(String, nullable=True)
    pais = Column(String, default="Perú")
    moneda = Column(String, default="PEN")
    estado = Column(String, default="activo")
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Datos tributarios del restaurante (emisor de boletas SUNAT).
    # Viven en el Cliente (tenant), no en config/env: cada restaurante tiene
    # su propio RUC. Ponerlo en config.py sería un bug de aislamiento
    # multi-tenant real — el día que se de de alta un segundo restaurante,
    # sus boletas saldrían emitidas con el RUC del primero.
    ruc = Column(String, nullable=True)
    # Para RUC persona natural con negocio (empieza con "10"), SUNAT registra
    # dos nombres distintos: la razón social (la persona: "Juan Joaquín
    # Aliaga Peña") y el nombre comercial, que es Cliente.nombre ("Pollería
    # Fogones", el que usa el resto de la app). No siempre son iguales —
    # nunca asumir uno a partir del otro.
    razon_social = Column(String, nullable=True)
    direccion = Column(String, nullable=True)  # Domicilio fiscal, para el encabezado de tickets/boletas

    # Correlativo de boletas (serie B001), incrementado atómicamente al
    # generar cada Factura. Vive acá y no como MAX(numero_correlativo)
    # calculado al vuelo porque esta app corre en un solo proceso uvicorn
    # (ver AUDITORIA/rate_limit en CLAUDE.md) pero SÍ puede recibir dos
    # cobros concurrentes de dos mozos distintos — un MAX+1 leído dos veces
    # antes de que el primer INSERT confirme repetiría número de boleta,
    # y SUNAT rechaza duplicados. Se protege ADEMÁS con un UNIQUE en
    # Factura(cliente_id, serie, numero_correlativo) como red de seguridad.
    boleta_correlativo_actual = Column(Integer, default=0, nullable=False)

    # Relationships
    usuarios = relationship("Usuario", back_populates="cliente", cascade="all, delete-orphan")
    platos = relationship("Plato", back_populates="cliente", cascade="all, delete-orphan")
    mesas = relationship("Mesa", back_populates="cliente", cascade="all, delete-orphan")
    comandas = relationship("Comanda", back_populates="cliente", cascade="all, delete-orphan")
    compras = relationship("Compra", back_populates="cliente", cascade="all, delete-orphan")
    # Categoria no tenía relación acá: borrar un cliente (superadmin →
    # "Eliminar") dejaba sus categorías huérfanas en la tabla — invisibles
    # en la app (todo se filtra por cliente_id) pero basura acumulándose
    # para siempre en la BD cada vez que se borra un restaurante.
    categorias = relationship("Categoria", cascade="all, delete-orphan")
    # Mismo caso que Categoria (ver arriba): sin esta relación, borrar un
    # cliente dejaba sus facturas —y las filas de factura_comandas que
    # cuelgan de ellas— huérfanas en la BD. Peor que con categorías: son
    # registros tributarios, justo lo que una auditoría iría a buscar.
    facturas = relationship("Factura", cascade="all, delete-orphan")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(String, primary_key=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False)
    nombre = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)  # Admin/superadmin. NULL para staff (mozo, cajero, cocinero)
    celular = Column(String, nullable=True)  # Staff (mozo, cajero, cocinero). NULL para admin
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="mozo")  # admin, mozo, cajero, cocinero
    estado = Column(String, default="activo")
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="usuarios")


class Categoria(Base):
    __tablename__ = "categorias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)
    # Un emoji, no una foto: identifica la categoría de un vistazo en el
    # selector de platos sin gastar red ni almacenamiento (a diferencia de
    # imagen_url en Plato, que sí sube un archivo real).
    icono = Column(String, nullable=False, default="🍽️")
    creado_en = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("cliente_id", "nombre", name="uq_cliente_categoria_nombre"),)


class Plato(Base):
    __tablename__ = "platos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)
    categoria = Column(String, nullable=False)
    precio_venta = Column(Float, nullable=False)
    descripcion = Column(Text, nullable=True)
    imagen_url = Column(String, nullable=True)
    estado = Column(String, default="activo")  # activo, inactivo
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="platos")
    comanda_platos = relationship("ComandaPlato", back_populates="plato", cascade="all, delete-orphan")


class Mesa(Base):
    __tablename__ = "mesas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    numero = Column(Integer, nullable=False)
    capacidad = Column(Integer, default=4)
    ubicacion = Column(String, nullable=True)
    estado = Column(String, default="disponible")  # disponible, ocupada
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Unique constraint: un número de mesa por cliente
    __table_args__ = (UniqueConstraint("cliente_id", "numero", name="uq_cliente_mesa_numero"),)

    # Relationships
    cliente = relationship("Cliente", back_populates="mesas")


class Comanda(Base):
    __tablename__ = "comandas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    numero_mesa = Column(Integer, nullable=False)
    total_cuenta = Column(Float, nullable=False)
    estado = Column(String, default="cocina")  # cocina, entregado, cobrado, cancelado
    creado_por = Column(String, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="comandas")
    comanda_platos = relationship("ComandaPlato", back_populates="comanda", cascade="all, delete-orphan")


class ComandaPlato(Base):
    __tablename__ = "comanda_platos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comanda_id = Column(Integer, ForeignKey("comandas.id"), nullable=False)
    plato_id = Column(Integer, ForeignKey("platos.id"), nullable=False)
    cantidad = Column(Integer, default=1)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    # Relationships
    comanda = relationship("Comanda", back_populates="comanda_platos")
    plato = relationship("Plato", back_populates="comanda_platos")


class Compra(Base):
    __tablename__ = "compras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    descripcion = Column(String, nullable=False)
    categoria = Column(String, nullable=True)
    monto = Column(Float, nullable=False)
    fecha = Column(String, nullable=False)  # YYYY-MM-DD
    estado = Column(String, default="registrado")  # registrado, cancelado
    creado_por = Column(String, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)

    # Relationships
    cliente = relationship("Cliente", back_populates="compras")


class AuditLog(Base):
    """
    Rastro de quién hizo qué, sobre qué, y cuándo — para acciones sensibles
    (login, alta/edición/baja de cuentas, cambios de contraseña, alta de
    restaurantes). Vive en su propia tabla (no en logs de texto) porque
    eso es justamente lo primero que pide una auditoría formal, y un log
    de texto se puede rotar o perder sin que quede registro de ello.
    """
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    actor = Column(String, nullable=False)  # email/celular/id de quien hizo la acción
    accion = Column(String, nullable=False)  # "login", "crear_usuario", "eliminar_usuario", etc.
    entidad = Column(String, nullable=False)  # "usuario", "cliente", "superadmin"
    entidad_id = Column(String, nullable=False)
    cliente_id = Column(String, nullable=True, index=True)  # null para acciones a nivel superadmin
    detalle = Column(String, nullable=True)


class Factura(Base):
    """
    Boleta electrónica emitida a SUNAT (vía proveedor Facturación.pe).

    Se genera a partir de comandas ya cobradas (Comanda.estado=='cobrado'),
    nunca a partir de una lista de platos que mande el frontend — el detalle
    (nombre/cantidad/precio) se copia de ComandaPlato en el momento de emitir,
    para que la boleta no pueda declarar algo distinto de lo que realmente
    se vendió (ver backend/routes/facturas.py).
    """
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)

    numero_mesa = Column(Integer, nullable=False)
    subtotal = Column(Float, nullable=False)  # Sin IGV
    igv = Column(Float, nullable=False)
    total = Column(Float, nullable=False)  # subtotal + igv

    # Fecha/hora LOCAL (Perú) de la primera emisión, congeladas al crear la
    # Factura — no derivar de creado_en (UTC) al exportar: un reintento
    # horas después NO debe cambiar la fecha de emisión del comprobante,
    # y cerca de medianoche UTC/local caen en días de calendario distintos
    # (el mismo bug que ya corrigieron en dashboard/compras, ver CLAUDE.md).
    fecha_emision_local = Column(String, nullable=True)  # YYYY-MM-DD
    hora_emision_local = Column(String, nullable=True)  # HH:MM:SS

    # Comprobante SUNAT (boleta = tipo 03, serie fija B001 para el MVP)
    tipo_comprobante = Column(String, default="03")
    serie = Column(String, default="B001")
    numero_correlativo = Column(Integer, nullable=False)

    # Datos del comprador — opcionales. "Público General" (sin documento) es
    # válido para una boleta; solo se piden si el cliente los solicita.
    tipo_documento_comprador = Column(String, nullable=True)  # "1"=DNI, "6"=RUC
    numero_documento_comprador = Column(String, nullable=True)
    nombre_comprador = Column(String, nullable=True)

    # Resultado del emisor usado (ver backend/config.py: emisor_facturacion).
    # pdf_url/qr_code/codigo_hash solo se llenan con el emisor "facturacion_pe"
    # (confirma con SUNAT en el momento); archivo_local solo con "sfs_local".
    pdf_url = Column(String, nullable=True)
    qr_code = Column(Text, nullable=True)  # data URI base64, puede ser largo
    codigo_hash = Column(String, nullable=True)  # Hash/CDR que devuelve SUNAT
    archivo_local = Column(String, nullable=True)  # Ruta del .cab escrito para el Facturador SUNAT

    # pendiente: recién creada, aún no se llamó al proveedor (o llamada en curso)
    # enviada_sunat: SUNAT la aceptó
    # error: el proveedor o SUNAT la rechazó (ver error_mensaje) — reintentable
    estado = Column(String, default="pendiente")
    error_mensaje = Column(String, nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow)
    enviado_en = Column(DateTime, nullable=True)

    cliente = relationship("Cliente", foreign_keys=[cliente_id], overlaps="facturas")
    # Sin este cascade, borrar una Factura (o el Cliente que la contiene)
    # dejaba sus filas de factura_comandas colgando: apuntando a un
    # factura_id que ya no existe.
    factura_comandas = relationship("FacturaComanda", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("cliente_id", "serie", "numero_correlativo", name="uq_cliente_serie_correlativo"),
    )


class CierreCaja(Base):
    """
    Apertura/cierre de caja física — un registro por TURNO (no por día: un
    restaurante puede abrir y cerrar varias veces el mismo día, ej. turno
    mañana / turno tarde — ver CLAUDE.md "Validador de Caja").

    Solo el admin abre y cierra (ver validar_admin en routes/caja.py). El
    flujo tiene DOS pasos separados en el tiempo, no un formulario único:
    - Apertura: admin cuenta el dinero que hay para empezar y lo declara.
      Sin esto no hay punto de partida contra el cual reconciliar.
    - Cierre: el sistema ya sabe cuánto se vendió/gastó DURANTE ESE TURNO
      (columnas calculadas, no ingresadas a mano — ver ventas_cobradas más
      abajo); el admin solo declara cuánto dinero HAY REALMENTE en la caja.
      La diferencia entre "debería haber" y "hay" es la señal de fraude/
      error que este validador existe para detectar.

    Solo puede haber UNA fila con estado='abierto' por cliente_id a la vez
    (lo impone POST /caja/abrir, no una constraint de BD) — pero SÍ puede
    haber varias filas cerradas con la misma `fecha` (varios turnos del
    mismo día). Por eso `fecha` NO tiene UniqueConstraint.

    Simplificación deliberada del MVP: ventas_cobradas y gastos_efectivo
    asumen que TODO el dinero registrado en Comanda/Compra es efectivo — la
    app todavía no distingue método de pago (efectivo/tarjeta/Yape). El día
    que eso se implemente, este cálculo debe filtrar por método de pago;
    hasta entonces, un restaurante que cobra con tarjeta verá diferencias
    en su cierre que NO son fraude, son ventas con tarjeta.
    """
    __tablename__ = "cierres_caja"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    fecha = Column(String, nullable=False)  # YYYY-MM-DD, día LOCAL en que se ABRIÓ este turno

    # Apertura
    saldo_inicial = Column(Float, nullable=False)
    abierto_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    abierto_por = Column(String, nullable=False)  # email del admin

    # Acumulado del TURNO (ventana abierto_en -> cerrado_en, no el día
    # calendario completo) — se calculan y congelan recién AL CERRAR (no se
    # recalculan después), para que el reporte impreso nunca cambie con el
    # tiempo. Usar el día completo rompería con turnos múltiples: el
    # segundo turno del día recontaría ventas que ya cerró el primero.
    ventas_cobradas = Column(Float, nullable=True)
    gastos_efectivo = Column(Float, nullable=True)
    retiros_personales = Column(Float, nullable=True)

    # Cierre
    saldo_esperado = Column(Float, nullable=True)  # inicial + ventas - gastos - retiros
    saldo_contado = Column(Float, nullable=True)   # lo que el admin contó físicamente
    diferencia = Column(Float, nullable=True)       # contado - esperado
    variacion_pct = Column(Float, nullable=True)
    razon_discrepancia = Column(String, nullable=True)

    cerrado_en = Column(DateTime, nullable=True)
    cerrado_por = Column(String, nullable=True)

    # abierto: aún no se cerró
    # cuadrado: cerrado por el admin, diferencia despreciable (<0.01)
    # discrepancia_leve: cerrado por el admin, |diferencia| <= 5
    # discrepancia_grave: cerrado por el admin, |diferencia| > 5
    # cerrado_automatico: el admin NUNCA la cerró y quedó de un día anterior
    #   — el sistema la cerró solo como válvula de seguridad para no bloquear
    #   Mesas/Cocina indefinidamente (ver _auto_cerrar_si_vencida en
    #   routes/caja.py). saldo_contado = saldo_esperado por falta de conteo
    #   físico real — NO es una prueba de que cuadró, requiere revisión.
    estado = Column(String, default="abierto", nullable=False)

    # Sin UniqueConstraint(cliente_id, fecha) a propósito: varios turnos
    # pueden compartir la misma fecha. "Solo una abierta a la vez" se
    # valida en la aplicación (routes/caja.py), no en el esquema.


class FacturaComanda(Base):
    """
    Asociación N:N entre Factura y Comanda (una boleta puede juntar varias
    comandas de la misma mesa si el mozo mandó más de un pedido antes de
    cobrar). Tabla de unión simple, sin columnas propias.
    """
    __tablename__ = "factura_comandas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False, index=True)
    comanda_id = Column(Integer, ForeignKey("comandas.id"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("factura_id", "comanda_id", name="uq_factura_comanda"),
    )
