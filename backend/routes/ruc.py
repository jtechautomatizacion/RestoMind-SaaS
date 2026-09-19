"""
Consulta de RUC contra el Padrón Reducido de SUNAT (copia local).

PARA QUÉ SIRVE
--------------
Cuando un comensal pide factura y dicta su RUC, el cajero tiene que tipear
la razón social exacta. Con esto la escribe el sistema: se valida el número
y se trae el nombre registrado en SUNAT. Menos tipeos, menos comprobantes
observados.

POR QUÉ VIVE ACÁ Y NO EN sunat-service
---------------------------------------
Se evaluó ponerlo en el contenedor de emisión y se descartó por tres
razones concretas:

  1. sunat-service guarda los certificados digitales y las credenciales SOL
     de todos los restaurantes. Es el componente más sensible del sistema.
     Sumarle un endpoint sin relación —con su propia superficie de ataque—
     va en contra de darle a cada pieza el mínimo alcance posible.
  2. Ese contenedor existe por UNA razón puntual: sunat-py exige
     cryptography<45 y RestoMind usa la 50. Un SELECT sobre SQLite no tiene
     ese conflicto, así que no gana nada estando aislado.
  3. Autenticación. sunat-service se protege con un token de servicio
     compartido, sin identidad de usuario ni cuotas. Esta consulta necesita
     exactamente lo contrario, y RestoMind ya tiene JWT y limitador.

Como RestoMind corre con systemd y no en Docker, la base se lee del disco
directamente: no hace falta ningún volumen ni salto de red.

DATOS PERSONALES (Ley N° 29733)
--------------------------------
Detrás de este endpoint hay ~19 millones de contribuyentes, y los RUC que
empiezan en 10/15/16/17 son personas naturales: su razón social es el
nombre y apellidos de alguien. El padrón es fuente de acceso público, así
que consultarlo es lícito, pero eso no vuelve lícito cualquier uso.

De ahí las tres restricciones de este archivo, que NO conviene relajar:
  - exige sesión válida (nunca público),
  - tiene cuota por IP: sin ella esto es una API de descarga masiva de
    datos personales, y un servidor que la expone es un blanco de scraping,
  - no registra en logs el RUC consultado ni el nombre devuelto.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.dependencies import get_cliente_id, get_superadmin_email, get_usuario_actual
from backend.models import ClienteFrecuente
from backend.schemas import (
    DocumentoConsultaResponse,
    DocumentoGuardarRequest,
    RucConsultaResponse,
    RucPadronEstadoResponse,
)
from backend.utils.padron import (
    PadronNoDisponible,
    consultar,
    consultar_dni_externo,
    formato_valido,
    info_padron,
)
from backend.utils.rate_limit import limitar_por_volumen
from backend.utils.security import validar_admin

router = APIRouter()

# 120 consultas cada 5 minutos por IP. Un restaurante con varias cajas rara
# vez pasa de unas pocas por minuto (solo se consulta cuando alguien pide
# factura), así que no estorba el uso real; un script que quiera bajarse el
# padrón, en cambio, tardaría años.
MAX_CONSULTAS = 120
VENTANA_SEGUNDOS = 5 * 60


def _consultar_en_padron(ruc: str, request: Request) -> RucConsultaResponse:
    """
    La consulta en sí, sin decidir QUIÉN puede hacerla.

    Está separada porque hay dos puertas legítimas con autenticaciones
    distintas —el restaurante y el superadmin— y las tres restricciones de
    protección de datos de la cabecera de este archivo tienen que valer igual
    para las dos. Duplicar el cuerpo era la forma segura de que un día una de
    las copias se quedara sin la cuota por IP.
    """
    limitar_por_volumen(request, "ruc", MAX_CONSULTAS, VENTANA_SEGUNDOS)

    ruc = ruc.strip()

    # Se valida ANTES de tocar la base: un número que no puede existir no
    # merece una consulta, y así el limitador no se gasta con basura.
    # formato_valido incluye el dígito verificador, que es lo que separa
    # "once dígitos" de "un RUC de verdad" y atrapa el tipeo del mostrador.
    if not formato_valido(ruc):
        raise HTTPException(
            status_code=400,
            detail="Ese RUC no es válido. Revisa que sean 11 dígitos y que estén bien copiados.",
        )

    try:
        contribuyente = consultar(ruc, settings.padron_db_path)
    except PadronNoDisponible as exc:
        # 503 y no 500: el servicio funciona, falta un paso de instalación.
        raise HTTPException(status_code=503, detail=str(exc))

    if contribuyente is None:
        # 200 con encontrado=False, no 404: "no está en el padrón" es una
        # respuesta legítima de la consulta, no un error. El cajero igual
        # puede emitir escribiendo el nombre a mano.
        return RucConsultaResponse(ruc=ruc, encontrado=False)

    return RucConsultaResponse(
        ruc=contribuyente.ruc,
        encontrado=True,
        nombre=contribuyente.nombre,
        estado=contribuyente.estado,
        condicion=contribuyente.condicion,
        persona_natural=contribuyente.persona_natural,
        puede_facturarse=contribuyente.puede_facturarse,
        # Se avisa ANTES de emitir, que es cuando todavía se puede corregir:
        # un contribuyente de baja o no habido puede hacer que SUNAT observe
        # el comprobante.
        advertencia=(
            None if contribuyente.puede_facturarse
            else f"Este RUC figura {contribuyente.estado} / {contribuyente.condicion} en SUNAT."
        ),
    )


@router.get("/ruc/{ruc}", response_model=RucConsultaResponse)
def consultar_ruc(
    ruc: str,
    request: Request,
    cliente_id: str = Depends(get_cliente_id),
) -> RucConsultaResponse:
    """
    Devuelve los datos de un RUC. Cualquier rol autenticado puede usarlo:
    quien cobra es quien necesita la razón social, y eso puede ser el mozo,
    el cajero o el dueño.
    """
    return _consultar_en_padron(ruc, request)


@router.get("/superadmin/ruc/{ruc}", response_model=RucConsultaResponse)
def consultar_ruc_superadmin(
    ruc: str,
    request: Request,
    email: str = Depends(get_superadmin_email),
) -> RucConsultaResponse:
    """
    La MISMA consulta, para el panel del superadmin.

    Hace falta una ruta aparte porque `get_cliente_id` exige un token de
    tipo "usuario" y rechaza el del superadmin con 403 — por diseño. Así que
    al dar de alta un restaurante, el panel pedía el RUC y la razón social a
    mano, teniendo el padrón a un SELECT de distancia: justo el tipeo que este
    módulo existe para evitar, y encima en el dato que después va impreso en
    cada comprobante.

    No se relajó la autenticación del endpoint del restaurante para que
    entrara también el superadmin: dejar que dos tipos de token pasen por la
    misma puerta convierte cada cambio futuro en esa puerta en una decisión
    sobre dos superficies a la vez.
    """
    return _consultar_en_padron(ruc, request)


@router.get("/ruc-padron/estado", response_model=RucPadronEstadoResponse)
def estado_padron(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
) -> RucPadronEstadoResponse:
    """
    Cuántos contribuyentes tiene la copia local y de cuándo es.

    Admin-only: le sirve para saber si el padrón quedó viejo (SUNAT lo
    actualiza a diario). Al resto del personal no le aporta nada, y el total
    de filas le diría a un curioso qué tan completa es la base.
    """
    validar_admin(db, usuario_actual, cliente_id)
    return RucPadronEstadoResponse(**info_padron(settings.padron_db_path))


# ============ CONSULTA UNIFICADA DE DOCUMENTO (DNI o RUC) ============
#
# El cajero tipea un número en un solo campo y no debería tener que saber
# qué es: el largo lo decide. 11 dígitos van al padrón de SUNAT; 8 dígitos
# son un DNI, que el padrón NO tiene, y se resuelven contra el registro
# propio del restaurante (y, si está configurado, un servicio externo).

@router.get("/documento/{numero}", response_model=DocumentoConsultaResponse)
def consultar_documento(
    numero: str,
    request: Request,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
) -> DocumentoConsultaResponse:
    limitar_por_volumen(request, "documento", MAX_CONSULTAS, VENTANA_SEGUNDOS)

    numero = numero.strip()

    if len(numero) == 11:
        return _consultar_ruc(numero)
    if len(numero) == 8 and numero.isdigit():
        return _consultar_dni(db, cliente_id, numero)

    raise HTTPException(
        status_code=400,
        detail="El documento debe tener 8 dígitos (DNI) u 11 dígitos (RUC).",
    )


def _consultar_ruc(ruc: str) -> DocumentoConsultaResponse:
    if not formato_valido(ruc):
        raise HTTPException(
            status_code=400,
            detail="Ese RUC no es válido. Revisá que los 11 dígitos estén bien copiados.",
        )
    try:
        contribuyente = consultar(ruc, settings.padron_db_path)
    except PadronNoDisponible as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if contribuyente is None:
        # 200 con encontrado=False, NO 400: "no está en el padrón" es una
        # respuesta legítima, no un error. Un RUC recién inscrito o una copia
        # local sin actualizar son casos normales, y el cajero resuelve
        # escribiendo la razón social a mano (requiere_nombre_manual se lo
        # dice al frontend). Con un 400, el cajero vería un error rojo por
        # algo que no hizo mal y que además tiene solución inmediata.
        return DocumentoConsultaResponse(
            documento=ruc, tipo="RUC", encontrado=False,
            requiere_nombre_manual=True,
            advertencia="No figura en el padrón. Escribí la razón social a mano.",
        )

    return DocumentoConsultaResponse(
        documento=ruc,
        tipo="RUC",
        encontrado=True,
        nombre=contribuyente.nombre,
        persona_natural=contribuyente.persona_natural,
        puede_facturarse=contribuyente.puede_facturarse,
        advertencia=(
            None if contribuyente.puede_facturarse
            else f"Este RUC figura {contribuyente.estado} / {contribuyente.condicion} en SUNAT."
        ),
    )


def _consultar_dni(db: Session, cliente_id: str, dni: str) -> DocumentoConsultaResponse:
    """
    Orden de búsqueda: primero lo que este restaurante ya conoce, después el
    servicio externo (que cuesta por consulta).

    El filtro por cliente_id no es opcional: el registro de comensales de un
    restaurante NO puede filtrarse a otro, aunque sea el mismo DNI.
    """
    guardado = (
        db.query(ClienteFrecuente)
        .filter(
            ClienteFrecuente.cliente_id == cliente_id,
            ClienteFrecuente.numero_documento == dni,
        )
        .first()
    )
    if guardado:
        guardado.usado_en = datetime.utcnow()
        db.commit()
        return DocumentoConsultaResponse(
            documento=dni, tipo="DNI", encontrado=True,
            nombre=guardado.nombre, origen="local",
        )

    nombre = consultar_dni_externo(dni)
    if nombre:
        # Se guarda para que la próxima visita de esta persona sea gratis e
        # instantánea. Finalidad acotada: emitir comprobantes (ver la nota de
        # datos personales en models.py:ClienteFrecuente).
        db.add(ClienteFrecuente(
            cliente_id=cliente_id, tipo_documento="1",
            numero_documento=dni, nombre=nombre, origen="api",
        ))
        db.commit()
        return DocumentoConsultaResponse(
            documento=dni, tipo="DNI", encontrado=True, nombre=nombre, origen="api",
        )

    return DocumentoConsultaResponse(
        documento=dni, tipo="DNI", encontrado=False,
        requiere_nombre_manual=True,
        advertencia="No lo tenemos registrado. Escribí el nombre a mano.",
    )


@router.post("/documento/{numero}", response_model=DocumentoConsultaResponse)
def recordar_documento(
    numero: str,
    payload: DocumentoGuardarRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
) -> DocumentoConsultaResponse:
    """
    Guarda el nombre que el cajero escribió a mano para un DNI.

    Así el trabajo de tipearlo se hace UNA vez: la próxima visita de ese
    comensal el nombre aparece solo, sin consultar ningún servicio de pago.

    Solo DNI: un RUC sale del padrón y no hay nada que recordar.
    """
    numero = numero.strip()
    if len(numero) != 8 or not numero.isdigit():
        raise HTTPException(status_code=400, detail="Solo se pueden recordar documentos DNI (8 dígitos).")

    nombre = " ".join(payload.nombre.split()).upper()
    if not nombre:
        raise HTTPException(status_code=400, detail="Falta el nombre.")

    guardado = (
        db.query(ClienteFrecuente)
        .filter(
            ClienteFrecuente.cliente_id == cliente_id,
            ClienteFrecuente.numero_documento == numero,
        )
        .first()
    )
    if guardado:
        guardado.nombre = nombre
        guardado.origen = "manual"
        guardado.usado_en = datetime.utcnow()
    else:
        db.add(ClienteFrecuente(
            cliente_id=cliente_id, tipo_documento="1",
            numero_documento=numero, nombre=nombre, origen="manual",
        ))
    db.commit()

    return DocumentoConsultaResponse(
        documento=numero, tipo="DNI", encontrado=True, nombre=nombre, origen="manual",
    )
