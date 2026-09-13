"""
Configuración operativa y activación del modo formal (facturación SUNAT).

Dos cosas viven acá:

  - El interruptor `usar_sunat`: si este restaurante emite comprobantes
    electrónicos desde RestoMind. Antes eso se deducía de "¿tiene RUC?", y
    mezclaba dos cosas distintas: tener RUC es un dato tributario del
    negocio; emitir desde ESTA app es una decisión operativa que además
    cambia con el tiempo (se vende desde el día uno, el certificado se
    consigue después).

  - La carga del certificado digital y las credenciales SOL, que es lo que
    de verdad habilita la emisión. Es un único paso a propósito: ver
    subir_certificado().
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual
from backend.models import Cliente
from backend.schemas import ConfiguracionResponse, ConfiguracionUpdateRequest
from backend.utils.auditoria import registrar_evento
from backend.utils.padron import (
    PadronNoDisponible,
    consultar as consultar_padron,
    formato_valido as formato_valido_ruc,
)
from backend.utils.security import validar_admin

router = APIRouter()

# Un .pfx real es una estructura DER y siempre arranca con SEQUENCE (0x30).
_DER_SEQUENCE = 0x30
# Un certificado tributario pesa unos pocos KB. El tope frena un archivo
# absurdo antes de escribir nada en disco.
MAX_PFX_BYTES = 512 * 1024

# RUC del ambiente de pruebas de SUNAT. Es público y fijo para todo el mundo
# (ver backend/scripts/crear_tenant_beta.py): sirve para que la pantalla
# avise que ahí NADA tiene efecto tributario, y precargue las credenciales
# de prueba en vez de hacer que alguien las busque en la documentación.
RUC_BETA = "20000000001"


def _configuracion_response(cliente: Cliente) -> ConfiguracionResponse:
    return ConfiguracionResponse(
        usar_sunat=bool(cliente.usar_sunat),
        tiene_ruc=bool(cliente.ruc),
        ruc=cliente.ruc,
        razon_social=cliente.razon_social,
        direccion_fiscal=cliente.direccion,
        # Con la facturación activa, los datos fiscales quedan congelados: el
        # certificado está emitido A NOMBRE de ese RUC, y cambiarlo dejaría
        # los comprobantes firmados por un contribuyente distinto del que
        # declaran. Apagar el interruptor los vuelve a liberar — un bloqueo
        # irreversible convertiría un tipeo en un callejón sin salida.
        datos_fiscales_bloqueados=bool(cliente.usar_sunat),
        emite_facturas=bool(cliente.emite_facturas),
        es_ambiente_beta=(cliente.ruc == RUC_BETA),
    )


@router.get("/configuracion", response_model=ConfiguracionResponse)
def obtener_configuracion(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario, cliente_id)

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    return _configuracion_response(cliente)


@router.post("/configuracion/subir-certificado", response_model=ConfiguracionResponse)
async def subir_certificado(
    ruc: str = Form(...),
    file: UploadFile = File(...),
    password: str = Form(...),
    # Usuario y clave SOL como TEXTO, no como archivo: pedirle a un dueño de
    # restaurante que arme un .txt de dos líneas es un paso que se hace mal
    # la mitad de las veces. El archivo lo escribe el servidor.
    sol_usuario: str = Form(...),
    sol_clave: str = Form(...),
    # El Padrón Reducido de SUNAT NO trae domicilio: al cargarlo se descartan
    # sus 11 columnas de dirección (ver cargar_padron_sunat.py — guardar el
    # domicilio de 19 millones de personas sin usarlo es acumulación
    # innecesaria, y baja la base de ~2,5 GB a ~1,6 GB). Así que la dirección
    # fiscal la aporta el propio restaurante, que obviamente la conoce.
    direccion_fiscal: str = Form(default=""),
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """
    Activa el modo formal: valida los datos fiscales, guarda el certificado y
    las credenciales SOL, y recién entonces prende `usar_sunat`.

    UN SOLO PASO, A PROPÓSITO
    -------------------------
    `sunat-service` necesita TRES archivos para poder firmar y enviar:
    certificado.pfx, clave.txt y sol.txt. Si el admin pudiera cargar solo
    algunos, el sistema quedaría "activado" y fallando en cada cobro con
    SIN_CREDENCIALES_SOL — que es exactamente el escenario de emisiones
    rotas que esta pantalla existe para evitar. O entra todo, o no se activa
    nada.

    DÓNDE VAN LOS ARCHIVOS
    ----------------------
    A {certs_dir}/{cliente_id}/, el mismo volumen que sunat-service monta de
    SOLO LECTURA: RestoMind escribe, el contenedor de firma lee. NUNCA a la
    base de datos — un .pfx con su clave permite emitir comprobantes a
    nombre del restaurante, y si alguien se lleva un backup de la BD no debe
    llevarse con qué facturar.

    El cliente_id sale del TOKEN, jamás del cuerpo: si viniera del payload,
    cualquier admin podría pisarle el certificado a otro restaurante.
    """
    validar_admin(db, usuario, cliente_id)

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    # ---- Paso A: datos fiscales ----
    ruc = (ruc or "").strip()
    if not formato_valido_ruc(ruc):
        raise HTTPException(
            status_code=400,
            detail="El RUC debe tener 11 dígitos y estar bien copiado (se verifica el dígito de control).",
        )

    # Si el restaurante ya tiene RUC guardado, el que llega DEBE coincidir:
    # cambiarlo acá dejaría el certificado apuntando a un contribuyente
    # distinto del que figura en los comprobantes ya emitidos.
    if cliente.ruc and cliente.ruc != ruc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Este restaurante ya está registrado con el RUC {cliente.ruc}. "
                "Para cambiarlo, pedíselo a quien te dio de alta el sistema."
            ),
        )

    razon_social = (cliente.razon_social or "").strip()
    if not razon_social:
        contribuyente = _buscar_en_padron(ruc)
        if contribuyente is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No encontramos el RUC {ruc} en el padrón de SUNAT. "
                    "Revisá el número, o pedí que registren la razón social y "
                    "la dirección fiscal del restaurante antes de continuar."
                ),
            )
        razon_social = contribuyente.nombre

    # ---- Los archivos se validan ANTES de escribir ninguno ----
    contenido_pfx = await file.read()
    _validar_pfx(contenido_pfx)
    if not password.strip():
        # .strip() solo para VALIDAR: una clave de puros espacios es un error
        # de tipeo. Lo que se GUARDA es el valor crudo — un .pfx puede tener
        # espacios al principio o al final y recortarlos rompería la firma.
        raise HTTPException(status_code=400, detail="Falta la clave del certificado.")

    sol_usuario, sol_clave = _validar_credenciales_sol(sol_usuario, sol_clave)

    # ---- Pasos C y D: escritura con permisos cerrados ----
    destino = Path(settings.certs_dir) / cliente_id
    try:
        destino.mkdir(parents=True, exist_ok=True)
        _cerrar_permisos(destino, 0o700)
        _escribir_privado(destino / "certificado.pfx", contenido_pfx)
        _escribir_privado(destino / "clave.txt", password.encode("utf-8"))
        _escribir_privado(
            destino / "sol.txt",
            (sol_usuario + "\n" + sol_clave + "\n").encode("utf-8"),
        )
    except OSError as exc:
        # Carpeta sin permisos, disco lleno, ruta inexistente. Se dice qué
        # pasó sin filtrar la ruta absoluta del servidor.
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo guardar el certificado en el servidor ({exc.__class__.__name__}).",
        )

    # ---- Pasos B y E: un solo commit, al final ----
    # Los datos fiscales y el interruptor se guardan JUNTOS y recién cuando
    # los tres archivos ya están en disco: si algo falla antes, el
    # restaurante queda exactamente como estaba, sin activarse a medias.
    ya_estaba = bool(cliente.usar_sunat)
    cliente.ruc = ruc
    cliente.razon_social = razon_social
    if direccion_fiscal.strip():
        cliente.direccion = direccion_fiscal.strip()
    cliente.usar_sunat = True
    db.commit()

    registrar_evento(
        db, actor=usuario, accion="subir_certificado", entidad="cliente",
        entidad_id=cliente_id, cliente_id=cliente_id,
        # Nunca la clave ni el contenido del certificado.
        detalle=f"certificado y credenciales SOL cargados (RUC {ruc})"
                + ("" if ya_estaba else "; usar_sunat: False -> True"),
    )

    return _configuracion_response(cliente)


def _buscar_en_padron(ruc: str):
    """El padrón no instalado se trata como "no lo encontré": el admin
    resuelve pidiendo que registren la razón social a mano, en vez de quedar
    bloqueado por 1,6 GB que todavía no se cargaron."""
    try:
        return consultar_padron(ruc, settings.padron_db_path)
    except PadronNoDisponible:
        return None
    except Exception:  # noqa: BLE001 — un fallo del padrón no puede tumbar la activación
        return None


def _validar_pfx(contenido: bytes) -> None:
    if not contenido:
        raise HTTPException(status_code=400, detail="El certificado llegó vacío.")
    if len(contenido) > MAX_PFX_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Ese archivo es demasiado grande para ser un certificado.",
        )
    # No se confía en la extensión ni en el content-type: los dos los elige
    # quien sube el archivo. Mismo criterio que la subida de fotos de plato.
    if contenido[0] != _DER_SEQUENCE:
        raise HTTPException(
            status_code=400,
            detail="Eso no parece un certificado .pfx. Revisá que sea el archivo que te dio tu proveedor.",
        )


def _validar_credenciales_sol(usuario: str, clave: str) -> tuple:
    """
    Comprueba que las credenciales SOL estén completas.

    Se valida acá y no dentro del contenedor de firma porque este es el único
    momento en que hay alguien mirando la pantalla para corregirlo: unas
    credenciales incompletas, descubiertas recién al cobrar, dejan la venta
    sin comprobante con el cliente ya en la puerta.

    El usuario SOL secundario va SIN el RUC adelante: sunat-py concatena
    {ruc}{usuario} por su cuenta al armar el UsernameToken. Pegar el RUC acá
    lo duplicaría y SUNAT rechazaría la autenticación.
    """
    usuario = (usuario or "").strip()
    # La clave NO se recorta: puede tener espacios significativos.
    if not usuario:
        raise HTTPException(status_code=400, detail="Falta el usuario SOL secundario.")
    if not (clave or "").strip():
        raise HTTPException(status_code=400, detail="Falta la clave SOL secundaria.")
    if chr(10) in usuario or chr(10) in clave:
        # sol.txt separa usuario y clave por salto de línea: un salto adentro
        # de cualquiera de los dos partiría el archivo mal.
        raise HTTPException(
            status_code=400,
            detail="El usuario y la clave SOL no pueden tener saltos de línea.",
        )
    return usuario, clave


def _cerrar_permisos(ruta: Path, modo: int) -> None:
    """
    En Linux (el VPS) aplica el modo de verdad. En Windows —el entorno de
    desarrollo— os.chmod solo sabe alternar el bit de solo-lectura y estos
    modos no existen, así que se intenta y se sigue: hacer fallar la carga
    por eso impediría probar el flujo completo en la máquina de desarrollo,
    donde además no hay certificados reales que proteger.
    """
    try:
        os.chmod(ruta, modo)
    except (OSError, NotImplementedError):
        pass


def _escribir_privado(ruta: Path, datos: bytes) -> None:
    """Escribe un archivo que solo el dueño puede leer (0600 en Linux).

    El chmod va DESPUÉS de escribir porque el contenido tiene que existir
    para poder cambiarle los permisos; la ventana entre ambos es de
    microsegundos y el directorio ya quedó en 0700."""
    ruta.write_bytes(datos)
    _cerrar_permisos(ruta, 0o600)


@router.patch("/configuracion", response_model=ConfiguracionResponse)
def actualizar_configuracion(
    payload: ConfiguracionUpdateRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario: str = Depends(get_usuario_actual),
):
    """Solo el admin del restaurante. El cliente_id sale del token, nunca
    del cuerpo: si viniera del payload, cualquiera podría apagarle la
    facturación a otro restaurante."""
    validar_admin(db, usuario, cliente_id)

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")

    if payload.usar_sunat and not cliente.ruc:
        # Sin RUC no hay comprobante posible: dejar prender el interruptor
        # solo llevaría al mismo toast rojo en cada cobro que este campo
        # existe para evitar, pero ahora sin explicación.
        raise HTTPException(
            status_code=400,
            detail="Para emitir boletas primero hay que cargar el certificado digital "
                   "y las credenciales SOL del restaurante.",
        )

    anterior = bool(cliente.usar_sunat)
    cliente.usar_sunat = payload.usar_sunat
    db.commit()

    # Solo se audita el cambio real: un PATCH que deja todo igual (el
    # frontend puede reenviar el estado actual) no es un evento.
    if anterior != payload.usar_sunat:
        registrar_evento(
            db, actor=usuario, accion="cambiar_configuracion", entidad="cliente",
            entidad_id=cliente_id, cliente_id=cliente_id,
            detalle=f"usar_sunat: {anterior} -> {payload.usar_sunat}",
        )

    return _configuracion_response(cliente)
