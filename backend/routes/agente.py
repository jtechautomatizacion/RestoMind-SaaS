"""
API para el agente que corre en la PC del restaurante y entrega los
comprobantes SUNAT al Facturador.

EL PROBLEMA QUE RESUELVE
------------------------
El Facturador SUNAT es una app de escritorio para Windows que vigila una
carpeta LOCAL. RestoMind, en cambio, corre en un VPS. No hay "carpeta
local compartida" entre los dos, y las alternativas obvias fallan:

  - Google Drive sincroniza cada archivo por separado y con su propia
    latencia, así que el Facturador puede ver el .cab minutos antes que su
    .det y procesar un comprobante incompleto.
  - Un recurso compartido SMB obliga a exponer el puerto 445 a internet
    (el vector de WannaCry) o a montar una VPN entre las dos máquinas.

La solución es invertir la dirección: en vez de que el servidor EMPUJE a
una carpeta que no alcanza, el agente CONSULTA y descarga. Así el
restaurante solo hace conexiones salientes —atraviesa cualquier router
casero sin abrir un solo puerto— y cada local se autentica con su propio
token, lo que de paso permite que un mismo RestoMind sirva a varios
restaurantes con sus respectivos Facturadores.

DE DÓNDE SALE EL CONTENIDO
--------------------------
Del disco del VPS: el exportador (utils/sfs_export.py) ya escribe los
cuatro archivos en settings.sfs_export_dir al emitir la boleta. Acá solo
se leen y se sirven. No se guarda una segunda copia en la base — sería el
mismo dato en dos lugares, con la posibilidad de que se desincronicen.
"""

from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.dependencies import get_cliente_id_agente
from backend.models import Cliente, Factura
from backend.schemas import (
    AgenteConfirmarRequest,
    AgentePendientesResponse,
    AgentePingResponse,
    ComprobanteParaDescargar,
)
from backend.utils.sfs_export import _nombre_base

router = APIRouter()

# Solo se entregan comprobantes efectivamente generados. Uno en 'error' o
# 'pendiente' no tiene archivos en disco todavía; se arregla desde
# Admin > Boletas (POST /facturas/{id}/reintentar), no por acá.
ESTADO_LISTO_PARA_ENTREGAR = "generado_localmente"

EXTENSIONES = ("cab", "det", "tri", "ley")


def _leer_archivos(factura: Factura, ruc_emisor: str) -> dict:
    """Lee los cuatro archivos del comprobante desde el disco del VPS.

    Devuelve None si falta alguno: un comprobante incompleto NO se entrega.
    Mandarle al Facturador tres de cuatro archivos es peor que no mandarle
    nada — se queda esperando el que falta, o peor, procesa algo a medias.
    """
    if not settings.sfs_export_dir:
        return None

    base = _nombre_base(
        ruc_emisor, factura.tipo_comprobante, factura.serie, factura.numero_correlativo
    )
    carpeta = Path(settings.sfs_export_dir)

    contenidos = {}
    for extension in EXTENSIONES:
        ruta = carpeta / f"{base}.{extension}"
        try:
            # Se lee en binario y se decodifica a mano para NO pasar por la
            # traducción de fin de línea del modo texto: el CRLF que el
            # formato exige tiene que llegar intacto hasta la carpeta del
            # Facturador.
            contenidos[extension] = ruta.read_bytes().decode(settings.sfs_export_encoding)
        except OSError:
            return None

    return {"nombre_base": base, **contenidos}


@router.get("/agente/ping", response_model=AgentePingResponse)
def ping(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id_agente),
):
    """Valida el token y dice cuántos comprobantes esperan, sin descargar
    nada. Es lo que corre el instalador para confirmar que el agente quedó
    bien configurado antes de dejarlo andando solo."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    pendientes = (
        db.query(Factura)
        .filter(
            Factura.cliente_id == cliente_id,
            Factura.estado == ESTADO_LISTO_PARA_ENTREGAR,
            Factura.descargado_en.is_(None),
        )
        .count()
    )
    return AgentePingResponse(
        cliente_id=cliente_id,
        cliente_nombre=cliente.nombre if cliente else "",
        pendientes=pendientes,
    )


@router.get("/agente/pendientes", response_model=AgentePendientesResponse)
def listar_pendientes(
    limite: int = 50,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id_agente),
):
    """Comprobantes generados que todavía no se confirmaron como entregados.

    El límite acota la respuesta si el agente estuvo días sin conexión: no
    tiene sentido mandarle 500 comprobantes de una: los baja de a tandas en
    vueltas sucesivas, y cada tanda que confirma es progreso que no se
    pierde si se corta la red a mitad.

    Orden ascendente por correlativo: las boletas se emiten en secuencia y
    conviene que el Facturador las procese en el mismo orden.
    """
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente or not cliente.ruc:
        # Sin RUC no se puede reconstruir el nombre de los archivos. No
        # debería pasar (no se emite una boleta sin RUC configurado), pero
        # es mejor una lista vacía que un 500 en un proceso desatendido.
        return AgentePendientesResponse(comprobantes=[])

    facturas = (
        db.query(Factura)
        .filter(
            Factura.cliente_id == cliente_id,
            Factura.estado == ESTADO_LISTO_PARA_ENTREGAR,
            Factura.descargado_en.is_(None),
        )
        .order_by(Factura.numero_correlativo.asc())
        .limit(max(1, min(limite, 200)))
        .all()
    )

    comprobantes = []
    for factura in facturas:
        archivos = _leer_archivos(factura, cliente.ruc)
        if archivos is None:
            # Los archivos no están en disco (carpeta rotada, borrada a
            # mano, o el comprobante viene de cuando RestoMind corría en
            # otra máquina). Se omite en silencio en vez de romper la tanda
            # entera: los demás comprobantes sí se pueden entregar, y este
            # sigue visible como pendiente para que el admin lo reintente
            # desde Admin > Boletas.
            continue
        comprobantes.append(ComprobanteParaDescargar(
            id=factura.id,
            numero_boleta=f"{factura.serie}-{factura.numero_correlativo:08d}",
            **archivos,
        ))

    return AgentePendientesResponse(comprobantes=comprobantes)


@router.post("/agente/confirmar", status_code=204)
def confirmar_descarga(
    payload: AgenteConfirmarRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id_agente),
):
    """El agente avisa que ya dejó los archivos en la carpeta del Facturador.

    El filtro por cliente_id no es decorativo: sin él, un token de un
    restaurante podría marcar como entregadas las boletas de otro, y esas
    desaparecerían de su cola sin haber llegado nunca a su Facturador.

    Solo sella las que todavía no tenían fecha, así que reconfirmar una
    tanda (el agente confirmó, se cortó la red antes de recibir la
    respuesta, y reintenta) no corre la fecha original de entrega.
    """
    ahora = datetime.utcnow()
    (
        db.query(Factura)
        .filter(
            Factura.cliente_id == cliente_id,
            Factura.id.in_(payload.ids),
            Factura.descargado_en.is_(None),
        )
        .update({Factura.descargado_en: ahora}, synchronize_session=False)
    )
    db.commit()
