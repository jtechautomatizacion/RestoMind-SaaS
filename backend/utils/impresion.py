"""
La cola de impresión: qué papel hace falta, quién lo toma y si salió.

POR QUÉ HAY UNA COLA Y NO UN AVISO
----------------------------------
La impresora térmica es Bluetooth y está emparejada a UN teléfono. Ningún
aparato puede escribirle a la impresora de otro, así que para que el ticket
salga en la cocina, el aparato de la cocina tiene que ser el que imprime — y
para eso tiene que enterarse de que hay algo para imprimir.

Un aviso sin memoria (un push, un websocket) se pierde si ese teléfono estaba
apagado, sin señal, con la app cerrada o con la impresora trabada, y NADIE se
entera de que un pedido nunca salió. En una cocina eso es un plato que no se
prepara. La cola convierte "avisar" en "encargar": queda escrito qué hacía
falta, quién lo tomó y cómo terminó.

LAS TRES REGLAS QUE HACEN QUE NO SE DUPLIQUE NI SE PIERDA
---------------------------------------------------------
1. Reclamar es un UPDATE condicionado por estado, no un SELECT seguido de un
   UPDATE. Dos aparatos que sondean a la vez no pueden llevarse el mismo
   trabajo: el segundo UPDATE ya no encuentra filas en 'pendiente'.
2. Un reclamo VENCE. Si el aparato que lo tomó se apagó antes de confirmar, el
   trabajo vuelve a la cola solo y lo toma otro. Sin esto, apagar el tablet de
   cocina dejaría ese pedido colgado para siempre.
3. Los reintentos tienen TOPE. Una impresora sin papel falla siempre; sin
   tope, ese trabajo se reintentaría eternamente y taparía a los que vienen
   atrás. Al llegar al tope queda 'fallido', que es visible y reimprimible.
"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Cliente,
    Comanda,
    TrabajoImpresion,
    ESTACIONES_IMPRESION,
)

# Cuánto puede tener un trabajo reclamado un aparato antes de que se asuma que
# no va a volver. Generoso a propósito: el ciclo normal (reclamar, conectar
# por Bluetooth, imprimir, confirmar) son segundos, pero una impresora lenta
# con varios papeles en fila puede tardar más — y devolver a la cola algo que
# SÍ se estaba imprimiendo produce un ticket duplicado, que es peor que
# esperar un minuto de más.
MINUTOS_RECLAMO_VENCE = 2

# Cuántas veces se reintenta antes de rendirse. Tres cubre lo transitorio (la
# impresora estaba ocupada con el papel anterior, el Bluetooth tardó en
# conectar) sin insistir con lo que no se va a arreglar solo, como que no haya
# papel.
MAX_INTENTOS = 3

# Cuánto sobrevive un trabajo que NADIE reclamó. Es el caso del local que no
# tiene impresora en esa estación: nadie va a venir a buscarlo nunca. Se marca
# 'vencido' en vez de dejarlo pendiente para siempre, porque un pendiente
# eterno ensucia la cola y hace que "hay trabajos sin imprimir" deje de
# significar algo.
MINUTOS_SIN_RECLAMAR_VENCE = 30


def _papeles_de_una_comanda(usar_sunat: bool) -> List[tuple]:
    """Qué papeles necesita un pedido recién tomado: (estación, tipo).

    Es el espejo de `_papelesAlPedir()` en frontend/js/print.js, con UNA
    diferencia deliberada: acá se encolan SIEMPRE los dos papeles, incluido el
    de cocina.

    En el frontend, el papel de cocina se omitía cuando el aparato estaba en
    "Atiendo solo" — tenía sentido cuando imprimía el mismo que tomaba el
    pedido, porque ese papel se tiraba sin leerlo. Con la cola eso ya no lo
    decide quien toma el pedido: si el local no atiende la estación de cocina,
    el trabajo simplemente vence solo (ver MINUTOS_SIN_RECLAMAR_VENCE). Poner
    esa decisión del lado del que encola volvería a atar "quién tomó el
    pedido" con "dónde sale el papel", que es exactamente lo que esta cola
    viene a separar.
    """
    return [
        ("cocina", "cocina"),
        ("mostrador", "precuenta" if usar_sunat else "preventa"),
    ]


def encolar_papeles_de_comanda(db: Session, comanda: Comanda) -> List[TrabajoImpresion]:
    """Encola los papeles de un pedido recién creado.

    NO hace commit: se engancha a la misma transacción que crea la comanda,
    para que no pueda existir un pedido sin sus papeles ni papeles de un
    pedido que falló al guardarse.
    """
    cliente = db.query(Cliente).filter(Cliente.id == comanda.cliente_id).first()
    usar_sunat = bool(cliente and cliente.usar_sunat)

    trabajos = []
    for estacion, tipo in _papeles_de_una_comanda(usar_sunat):
        trabajo = TrabajoImpresion(
            cliente_id=comanda.cliente_id,
            estacion=estacion,
            tipo_documento=tipo,
            comanda_id=comanda.id,
        )
        db.add(trabajo)
        trabajos.append(trabajo)
    return trabajos


def _mantenimiento(db: Session, cliente_id: str) -> None:
    """Devuelve a la cola lo que quedó colgado y jubila lo que nadie va a venir
    a buscar. Corre al principio de cada reclamo — así no hace falta un cron
    aparte, igual que `_auto_cerrar_si_vencida` en routes/caja.py."""
    ahora = datetime.utcnow()

    # 1. Reclamos vencidos -> vuelven a la cola (o se rinden si ya insistieron
    #    demasiado). El aparato que los tenía se apagó, perdió señal, o la app
    #    se cerró a mitad del trabajo.
    vencidos = (
        db.query(TrabajoImpresion)
        .filter(
            TrabajoImpresion.cliente_id == cliente_id,
            TrabajoImpresion.estado == "reclamado",
            TrabajoImpresion.reclamado_en < ahora - timedelta(minutes=MINUTOS_RECLAMO_VENCE),
        )
        .all()
    )
    for t in vencidos:
        if t.intentos >= MAX_INTENTOS:
            t.estado = "fallido"
            t.error = t.error or "El aparato que lo tomó no confirmó si salió"
        else:
            t.estado = "pendiente"
            t.reclamado_por = None
            t.reclamado_en = None

    # 2. Pendientes que nadie reclamó nunca -> vencidos. El local no atiende
    #    esa estación; no es un error, es un papel que nadie pidió.
    db.query(TrabajoImpresion).filter(
        TrabajoImpresion.cliente_id == cliente_id,
        TrabajoImpresion.estado == "pendiente",
        TrabajoImpresion.creado_en < ahora - timedelta(minutes=MINUTOS_SIN_RECLAMAR_VENCE),
    ).update({"estado": "vencido"}, synchronize_session=False)


def reclamar_trabajos(
    db: Session,
    cliente_id: str,
    estaciones: List[str],
    device_id: str,
    limite: int = 5,
) -> List[TrabajoImpresion]:
    """Toma para este aparato los papeles pendientes de las estaciones que
    atiende, y le devuelve TAMBIÉN los que ya tenía tomados y no confirmó.

    Devolver lo propio sin confirmar es lo que hace que un corte a mitad de
    camino se recupere solo: si la app se recargó justo después de reclamar
    pero antes de imprimir, en el sondeo siguiente esos papeles vuelven a
    aparecer sin esperar a que venza el reclamo.

    El reclamo es un UPDATE condicionado por `estado == 'pendiente'`, no un
    SELECT y después un UPDATE: dos aparatos sondeando a la vez no pueden
    llevarse el mismo trabajo, porque el segundo UPDATE ya no lo encuentra
    pendiente.
    """
    estaciones = [e for e in estaciones if e in ESTACIONES_IMPRESION]
    if not estaciones or not device_id:
        return []

    _mantenimiento(db, cliente_id)

    ahora = datetime.utcnow()

    # Los más viejos primero: en una cocina, el orden de llegada ES el orden de
    # preparación.
    candidatos = (
        select(TrabajoImpresion.id)
        .where(
            TrabajoImpresion.cliente_id == cliente_id,
            TrabajoImpresion.estado == "pendiente",
            TrabajoImpresion.estacion.in_(estaciones),
        )
        .order_by(TrabajoImpresion.creado_en.asc())
        .limit(limite)
    )

    db.query(TrabajoImpresion).filter(
        TrabajoImpresion.id.in_(candidatos),
        # Repetir la condición acá no es redundante: es lo que cierra la
        # carrera. Entre armar la subconsulta y aplicar el UPDATE, otro
        # aparato pudo haberse llevado esas filas.
        TrabajoImpresion.estado == "pendiente",
    ).update(
        {
            "estado": "reclamado",
            "reclamado_por": device_id,
            "reclamado_en": ahora,
            "intentos": TrabajoImpresion.intentos + 1,
        },
        synchronize_session=False,
    )
    db.commit()

    return (
        db.query(TrabajoImpresion)
        .filter(
            TrabajoImpresion.cliente_id == cliente_id,
            TrabajoImpresion.estado == "reclamado",
            TrabajoImpresion.reclamado_por == device_id,
            # Acotado a las estaciones que atiende AHORA, no a las que atendía
            # cuando lo reclamó. Si al aparato del mozo le sacan la estación de
            # cocina (porque la cocina ya tiene su impresora), lo que haya
            # alcanzado a reclamar antes NO tiene que seguir saliendo por su
            # impresora: se lo deja vencer y lo toma el de la cocina. Sin este
            # filtro, cambiar la configuración no surtía efecto hasta que se
            # vaciara lo que ese aparato ya tenía tomado.
            TrabajoImpresion.estacion.in_(estaciones),
        )
        .order_by(TrabajoImpresion.creado_en.asc())
        .all()
    )


def confirmar_resultado(
    db: Session,
    cliente_id: str,
    trabajo_id: int,
    device_id: str,
    salio: bool,
    error: Optional[str] = None,
) -> Optional[TrabajoImpresion]:
    """Cierra un trabajo. Solo puede cerrarlo el aparato que lo tomó.

    Esa restricción evita que un aparato marque como impreso un papel que salió
    (o no salió) por otra impresora: el único que sabe si salió es el que lo
    intentó.
    """
    trabajo = (
        db.query(TrabajoImpresion)
        .filter(
            TrabajoImpresion.id == trabajo_id,
            TrabajoImpresion.cliente_id == cliente_id,
            TrabajoImpresion.reclamado_por == device_id,
        )
        .first()
    )
    if not trabajo:
        return None

    if salio:
        trabajo.estado = "impreso"
        trabajo.impreso_en = datetime.utcnow()
        trabajo.error = None
    else:
        trabajo.error = (error or "No se pudo imprimir")[:300]
        # Se rinde recién al llegar al tope; hasta entonces vuelve a la cola
        # para que lo tome de nuevo (puede ser esta misma impresora cuando le
        # pongan papel, o la de otro puesto).
        if trabajo.intentos >= MAX_INTENTOS:
            trabajo.estado = "fallido"
        else:
            trabajo.estado = "pendiente"
            trabajo.reclamado_por = None
            trabajo.reclamado_en = None

    db.commit()
    return trabajo


def reimprimir(db: Session, cliente_id: str, comanda_id: int, tipo_documento: str, estacion: str):
    """Vuelve a pedir un papel, como un trabajo NUEVO.

    No se reabre el original: el historial tiene que poder decir cuántas veces
    salió algo y por qué. Un trabajo reabierto borraría la primera salida, que
    es justo el dato que se busca cuando alguien pregunta "¿esto ya se imprimió?".
    """
    comanda = (
        db.query(Comanda)
        .filter(Comanda.id == comanda_id, Comanda.cliente_id == cliente_id)
        .first()
    )
    if not comanda:
        return None

    original = (
        db.query(TrabajoImpresion)
        .filter(
            TrabajoImpresion.cliente_id == cliente_id,
            TrabajoImpresion.comanda_id == comanda_id,
            TrabajoImpresion.tipo_documento == tipo_documento,
        )
        .order_by(TrabajoImpresion.creado_en.asc())
        .first()
    )

    trabajo = TrabajoImpresion(
        cliente_id=cliente_id,
        estacion=estacion,
        tipo_documento=tipo_documento,
        comanda_id=comanda_id,
        reimpresion_de=original.id if original else None,
    )
    db.add(trabajo)
    db.commit()
    db.refresh(trabajo)
    return trabajo
