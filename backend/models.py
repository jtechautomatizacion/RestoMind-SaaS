from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, UniqueConstraint, Index, text
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

    # ¿Este restaurante emite boletas electrónicas desde RestoMind?
    #
    # Antes esto se deducía de "tiene RUC o no", y eso mezclaba dos cosas
    # distintas: tener RUC es un dato tributario del negocio; emitir boletas
    # desde ESTA app es una decisión operativa. Un restaurante con RUC que
    # factura por otro medio (o que todavía no configuró su Facturador)
    # recibía un toast rojo en CADA cobro —"la boleta NO se emitió"— y se le
    # llenaba Admin > Boletas de pendientes que nadie iba a emitir nunca.
    #
    # Default False a propósito: un restaurante nuevo vende desde el primer
    # día y configura SUNAT después, no al revés. Solo puede ponerse en True
    # si hay RUC cargado (lo valida PATCH /clientes/configuracion).
    usar_sunat = Column(Boolean, default=False, nullable=False)

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
    insumos = relationship("Insumo", back_populates="cliente", cascade="all, delete-orphan")


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
    # Cascade a nivel ORM (no DB): SQLite no aplica ON DELETE CASCADE sin
    # PRAGMA foreign_keys=ON, que esta app no activa. Con delete-orphan, el
    # db.delete(usuario) de routes/usuarios.py limpia sus tokens push —
    # si no, quedarían huérfanos y, peor, una cuenta nueva creada después
    # con el mismo id heredaría los avisos del empleado anterior.
    push_subscriptions = relationship(
        "PushSubscription", back_populates="usuario", cascade="all, delete-orphan",
    )


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


class Insumo(Base):
    """
    Stock de almacén (pescado, limón, ají...) con un mínimo por insumo para
    avisar antes de quedarse sin nada a mitad de un servicio.

    Deliberadamente DESACOPLADO de Compra: registrar un gasto no mueve el
    stock, y mover el stock no registra un gasto. Son dos preguntas
    distintas —"cuánto gasté" (financiero, ya resuelto en Compra) y "cuánto
    me queda" (físico, esto)— y atarlas haría divergir el stock teórico del
    real, porque en un restaurante hay mermas, desperdicio y compras que no
    entran a almacén. El admin ajusta la cantidad con lo que cuenta de
    verdad, que es el único número en el que puede confiar.
    """
    __tablename__ = "insumos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    nombre = Column(String, nullable=False)
    unidad = Column(String, nullable=False)  # kg, litro, unidad, docena...
    cantidad_actual = Column(Float, nullable=False)
    cantidad_minima = Column(Float, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("cliente_id", "nombre", name="uq_cliente_insumo_nombre"),)

    # Relationships
    cliente = relationship("Cliente", back_populates="insumos")
    movimientos = relationship("MovimientoInsumo", back_populates="insumo", cascade="all, delete-orphan")


class MovimientoInsumo(Base):
    """
    Cada entrada o salida de stock, con quién la hizo y por qué.

    Insumo.cantidad_actual es el saldo; esta tabla es el extracto que lo
    explica. Sin ella, un stock que no cuadra es un callejón sin salida:
    el admin ve "quedan 3kg" sin poder saber si fue una salida mal tipeada,
    una merma no anotada o alguien llevándose mercadería. Con el historial,
    esa pregunta se responde mirando las filas.

    El saldo se mantiene en Insumo y NO se recalcula sumando movimientos:
    la carga de insumos existentes no tiene movimiento de origen (el admin
    escribió el stock a mano al darlos de alta), así que SUM(movimientos)
    daría un número distinto del real desde la primera fila.
    """
    __tablename__ = "movimientos_insumo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    insumo_id = Column(Integer, ForeignKey("insumos.id"), nullable=False, index=True)

    tipo = Column(String, nullable=False)  # "entrada" | "salida"
    cantidad = Column(Float, nullable=False)  # Siempre positiva; el signo lo da 'tipo'
    razon = Column(String, nullable=False)  # compra, uso, ajuste, merma, reversion, otro

    # Saldo del insumo DESPUÉS de aplicar este movimiento, congelado acá.
    # Es redundante con Insumo.cantidad_actual solo para el último
    # movimiento; para los anteriores es la única forma de reconstruir el
    # historial ("¿cuánto había el martes?") sin re-sumar toda la cadena,
    # que además fallaría por lo dicho en el docstring de la clase.
    saldo_despues = Column(Float, nullable=False)

    # Fecha de negocio: cuándo ocurrió el movimiento en la vida real (el
    # admin puede registrar hoy una merma de ayer). Distinta de creado_en,
    # que es cuándo se tipeó en el sistema — la auditoría necesita las dos.
    fecha = Column(DateTime, nullable=False)

    # FK real al usuario, NO el 'sub' del JWT: ese vale email para el admin
    # pero código de acceso para el staff, y las cuentas de staff se crean
    # con email=None (ver la lección de push_subscriptions en CLAUDE.md).
    usuario_id = Column(String, ForeignKey("usuarios.id"), nullable=True)
    # Nombre congelado al momento del movimiento: si la cuenta se elimina
    # después, el historial debe seguir diciendo quién lo hizo.
    usuario_nombre = Column(String, nullable=True)

    # Deshacer un movimiento NO borra su fila: agrega una inversa que apunta
    # acá. Borrarla haría desaparecer justo lo que hay que auditar (el error
    # y quién lo cometió) y dejaría un ajuste suelto sin explicación. Es el
    # mismo criterio que un contra-asiento contable.
    revierte_a_id = Column(Integer, ForeignKey("movimientos_insumo.id"), nullable=True)
    # Marca en el original. Sin esto, dos clicks al botón de deshacer
    # descuentan el doble y dejan el stock peor que el error a corregir.
    revertido = Column(Boolean, default=False, nullable=False)

    creado_en = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_movimientos_insumo_historial", "cliente_id", "insumo_id", "creado_en"),
    )

    # Relationships
    insumo = relationship("Insumo", back_populates="movimientos")


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
    # Cuándo el agente de la PC del restaurante confirmó que los cuatro
    # archivos llegaron a la carpeta del Facturador (ver routes/agente.py).
    # Nulo = generado en el VPS pero todavía sin entregar.
    #
    # Es el registro DURABLE de qué se entregó: el agente lleva su propio
    # control local para no escribir dos veces, pero ese control vive en una
    # PC de restaurante que se puede reinstalar. Sin esta columna, perder esa
    # PC significaría no poder saber qué boletas nunca llegaron a SUNAT.
    descargado_en = Column(DateTime, nullable=True)

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

    Solo puede haber UNA fila con estado='abierto' por cliente_id a la vez.
    Lo imponen DOS cosas: el chequeo de POST /caja/abrir (que da el mensaje
    de error legible) y el índice único parcial de __table_args__ (que
    cierra la carrera entre dos requests simultáneos — un doble clic del
    admin, o dos pestañas abiertas, alcanzaban para dejar dos turnos
    abiertos, y entonces las mismas ventas se contaban en los dos y la caja
    no cuadraba nunca). SÍ puede haber varias filas CERRADAS con la misma
    `fecha` (varios turnos del mismo día): por eso `fecha` no es única y el
    índice filtra por estado='abierto'.

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
    # Etiqueta opcional ("Mañana", "Tarde", "Noche") para distinguir turnos
    # en el historial a simple vista, sin calcular a qué hora empezó cada
    # uno. Sin ella (turnos viejos, o quien no la usa), el frontend cae de
    # vuelta a "Turno N de hoy" — ver GET /caja/estado.
    nombre_turno = Column(String, nullable=True)
    # Zona horaria del restaurante, capturada del dispositivo del ADMIN al
    # abrir el turno. El auto-cierre de turnos vencidos necesita saber qué
    # día local es "hoy", y antes lo tomaba del header X-TZ-Offset de quien
    # consultaba — pero /caja/gate lo consulta cualquier rol, así que un
    # mozo mandando un offset falso podía adelantar el "hoy" y forzar el
    # cierre automático del turno que el admin tenía abierto y validado.
    # Guardarlo acá lo vuelve un dato del turno, no del que pregunta.
    tz_offset = Column(Integer, default=0, nullable=False)

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
    # pueden compartir la misma fecha (turno mañana y turno tarde).
    #
    # Lo que sí es único es "un turno ABIERTO por restaurante", y por eso el
    # índice es PARCIAL (WHERE estado='abierto'): así no estorba a los
    # cerrados. routes/caja.py ya chequeaba esto antes de insertar, pero un
    # check-then-insert sin lock no sirve contra dos requests a la vez —
    # bastaba un doble clic del admin, o dos pestañas abiertas, para dejar
    # dos turnos abiertos. Con dos, .first() elige uno cualquiera y las
    # mismas ventas se cuentan en ambos: la caja no vuelve a cuadrar nunca.
    # La BD es el único lugar donde esa regla se puede imponer de verdad.
    __table_args__ = (
        Index(
            "ix_cierres_caja_un_turno_abierto",
            "cliente_id",
            unique=True,
            sqlite_where=text("estado = 'abierto'"),
        ),
    )


class PushSubscription(Base):
    """
    Token FCM (Firebase Cloud Messaging) de un dispositivo que quiere recibir
    notificaciones push — hoy solo se usa para avisar de una comanda nueva,
    incluso con la app minimizada (ver utils/push_notifications.py). Un
    usuario puede tener varios tokens (un tablet fijo en cocina + su celular),
    por eso no hay un token por fila de Usuario sino esta tabla aparte.

    El vínculo es `usuario_id` (FK real), NUNCA el 'sub' del JWT: ese campo
    vale el EMAIL para admin/superadmin pero el CÓDIGO DE ACCESO para el
    staff (ver auth.py:login_staff, que hace crear_token(email=usuario.celular)),
    y las cuentas de staff tienen email=NULL (usuarios.py:crear_staff). Una
    versión anterior guardaba ese 'sub' en una columna `usuario_email` y
    hacía el join contra Usuario.email — lo que en la práctica significaba
    que jefe_cocina, el rol para el que existe este feature, NUNCA recibía
    nada (NULL nunca matchea el código). La FK elimina esa clase de bug de
    raíz y de paso permite el cascade de abajo.

    El token en sí lo entrega el SDK de Firebase en el navegador — este
    backend nunca genera ni valida su formato, solo lo guarda y se lo pasa
    a la Admin SDK de Firebase al enviar.
    """
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    usuario_id = Column(String, ForeignKey("usuarios.id"), nullable=False, index=True)
    token = Column(String, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="push_subscriptions")

    __table_args__ = (
        UniqueConstraint("usuario_id", "token", name="uq_push_usuario_token"),
    )


class AgenteToken(Base):
    """
    Credencial del agente que corre en la PC del restaurante y baja los
    comprobantes SUNAT para dejárselos al Facturador (ver routes/agente.py).

    Por qué un token propio y no el JWT de un usuario:
    - Un JWT expira a las 12 h; el agente tiene que poder trabajar meses sin
      que nadie toque esa PC.
    - Un JWT de admin daría acceso a TODO el restaurante (caja, personal,
      finanzas) desde una PC que está en el salón de un local. Este token
      solo sirve para las rutas de /api/agente/*.
    - Un JWT no se puede revocar (limitación conocida, ver
      PRODUCTION_READINESS.md). Este sí: se marca estado='revocado' y deja
      de funcionar en el próximo request.

    Se guarda HASHEADO con bcrypt, igual que una contraseña: vive en el
    disco de una PC ajena, así que hay que poder revocarlo pero nunca
    volver a leerlo. Se muestra una sola vez, al generarlo con
    backend/scripts/crear_token_agente.py.
    """
    __tablename__ = "agente_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cliente_id = Column(String, ForeignKey("clientes.id"), nullable=False, index=True)
    # Para distinguirlos si un restaurante tiene más de una caja con su
    # propio Facturador ("Caja principal", "Terraza").
    nombre = Column(String, nullable=False)
    token_hash = Column(String, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)
    # Permite ver desde el VPS si un agente dejó de reportarse (PC apagada,
    # sin internet, tarea programada borrada) ANTES de que el restaurante
    # llame porque no le salen las boletas.
    ultimo_uso_en = Column(DateTime, nullable=True)
    estado = Column(String, default="activo")  # activo | revocado


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
