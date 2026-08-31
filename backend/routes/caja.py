"""
Validador de Caja — apertura/cierre por TURNO, solo admin.

Un restaurante puede tener varios turnos el mismo día (mañana/tarde) — cada
uno es su propia apertura/cierre, con su propio reporte. Lo único que la
app impone es "no se puede abrir un turno nuevo mientras haya uno abierto":

  1. POST /caja/abrir   — declara saldo_inicial, arranca el turno
  2. ...   el turno opera normal (comandas, compras)  ...
  3. POST /caja/cerrar  — declara saldo_contado; el sistema calcula
     ventas/gastos DE ESE TURNO (no del día completo) y la diferencia
     contra lo que "debería haber".
  4. Se puede abrir el siguiente turno de inmediato — no hay que esperar
     al día siguiente.

Ventas y gastos de un turno se calculan por VENTANA DE TIEMPO exacta
(abierto_en -> cerrado_en, o "ahora" mientras sigue abierto), nunca por
día calendario completo — con turnos múltiples, sumar por día completo
haría que el segundo turno del día recontara las ventas que ya cerró el
primero. Como los turnos nunca se solapan (solo uno "abierto" a la vez),
ventanas de tiempo disjuntas garantizan que cada sol se cuenta una sola vez.

Válvula de seguridad — auto-cierre de turno vencido (_auto_cerrar_si_vencida):
Mesas y Cocina exigen un turno abierto HOY para operar (GET /caja/gate). Si
el admin genuinamente se olvida de cerrar una noche, el restaurante entero
quedaría congelado al día siguiente hasta que alguien lo note. Para evitar
ese bloqueo total, /caja/estado, /caja/gate y /caja/abrir primero revisan si
el turno abierto quedó de un día ANTERIOR al de hoy; si es así, se cierra
solo con saldo_contado = saldo_esperado (no hay conteo físico real que usar)
y queda marcado estado='cerrado_automatico' —nunca 'cuadrado'— para que
quede clarísimo que ese cierre no fue validado por un conteo real. Esto NO
afloja la regla "hay que cerrar para abrir otro": el sistema solo resuelve
por vos el turno que quedó pendiente de un día que ya pasó.
"""

from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_cliente_id, get_usuario_actual, get_tz_offset
from backend.models import Comanda, Compra, CierreCaja
from backend.schemas import (
    AbrirCajaRequest,
    CerrarCajaRequest,
    CierreCajaResponse,
    CajaEstadoResponse,
    CajaGateResponse,
)
from backend.utils.auditoria import registrar_evento
from backend.utils.security import validar_admin

router = APIRouter()

# Por debajo de este monto, una diferencia se considera ruido de vueltos
# (redondeo de moneditas) y no una discrepancia real.
UMBRAL_CUADRADO = 0.01
UMBRAL_DISCREPANCIA_GRAVE = 5.0


def _hoy_local(tz_offset: int) -> date:
    desfase = timedelta(minutes=tz_offset)
    return (datetime.utcnow() - desfase).date()


def _calcular_ventas_gastos_periodo(db: Session, cliente_id: str, desde_dt: datetime, hasta_dt: datetime) -> tuple:
    """
    Ventas y gastos DENTRO de la ventana exacta en que el turno estuvo
    abierto — no del día calendario completo (ver docstring del módulo).

    Gastos usa Compra.creado_en (el timestamp real de cuándo se registró en
    el sistema), NO Compra.fecha (una fecha de calendario sin hora, elegida
    a mano por el admin al crear el gasto) — fecha no tiene resolución
    suficiente para ubicar un gasto dentro de un turno específico.
    """
    ventas = (
        db.query(Comanda)
        .filter(
            Comanda.cliente_id == cliente_id,
            Comanda.estado == "cobrado",
            Comanda.actualizado_en >= desde_dt,
            Comanda.actualizado_en <= hasta_dt,
        )
        .all()
    )
    total_ventas = round(sum(c.total_cuenta for c in ventas), 2)

    gastos = (
        db.query(Compra)
        .filter(
            Compra.cliente_id == cliente_id,
            Compra.estado == "registrado",
            Compra.creado_en >= desde_dt,
            Compra.creado_en <= hasta_dt,
        )
        .all()
    )
    total_gastos = round(sum(c.monto for c in gastos), 2)

    return total_ventas, total_gastos


def _clasificar_estado(diferencia: float) -> str:
    abs_dif = abs(diferencia)
    if abs_dif < UMBRAL_CUADRADO:
        return "cuadrado"
    if abs_dif <= UMBRAL_DISCREPANCIA_GRAVE:
        return "discrepancia_leve"
    return "discrepancia_grave"


def _auto_cerrar_si_vencida(db: Session, cliente_id: str, tz_offset: int) -> None:
    """Ver docstring del módulo ("Válvula de seguridad"). Se llama al
    principio de /caja/estado, /caja/gate y /caja/abrir — así el auto-cierre
    ocurre en el primer request del día sin necesitar un cron aparte."""
    caja = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado == "abierto")
        .first()
    )
    if not caja:
        return

    hoy = _hoy_local(tz_offset)
    fecha_caja = date.fromisoformat(caja.fecha)
    if fecha_caja >= hoy:
        return  # sigue siendo un turno de hoy — nada que auto-cerrar

    ahora = datetime.utcnow()
    ventas, gastos = _calcular_ventas_gastos_periodo(db, cliente_id, caja.abierto_en, ahora)
    saldo_esperado = round(caja.saldo_inicial + ventas - gastos, 2)

    caja.ventas_cobradas = ventas
    caja.gastos_efectivo = gastos
    caja.retiros_personales = 0.0
    caja.saldo_esperado = saldo_esperado
    # Sin conteo físico real disponible: se asume igual al esperado. No es
    # una prueba de que cuadró, es el mejor dato que hay — por eso el estado
    # queda marcado aparte (nunca 'cuadrado') para que el admin lo revise.
    caja.saldo_contado = saldo_esperado
    caja.diferencia = 0.0
    caja.variacion_pct = 0.0
    caja.razon_discrepancia = (
        f"Cierre automático: este turno (abierto el {caja.fecha}) quedó sin cerrar "
        "y ya pasó su día. No refleja un conteo físico real — revisar manualmente."
    )
    caja.cerrado_en = ahora
    caja.cerrado_por = "sistema (cierre automático)"
    caja.estado = "cerrado_automatico"

    db.commit()

    registrar_evento(
        db, actor="sistema", accion="cerrar_caja_automatico", entidad="cierre_caja",
        entidad_id=caja.id, cliente_id=cliente_id,
        detalle=f"fecha: {caja.fecha}, saldo_esperado: {saldo_esperado}",
    )


@router.get("/caja/gate", response_model=CajaGateResponse)
def verificar_gate_caja(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    tz_offset: int = Depends(get_tz_offset),
):
    """
    Semáforo para Mesas/Cocina: ¿hay un turno abierto HOY? Sin validar_admin
    a propósito — mozo/cocina también necesitan saber si pueden operar, y a
    diferencia de /caja/estado esta ruta nunca expone montos (eso es
    información financiera privada del admin).
    """
    _auto_cerrar_si_vencida(db, cliente_id, tz_offset)

    hoy = _hoy_local(tz_offset)
    turno_hoy_abierto = (
        db.query(CierreCaja)
        .filter(
            CierreCaja.cliente_id == cliente_id,
            CierreCaja.estado == "abierto",
            CierreCaja.fecha == hoy.isoformat(),
        )
        .first()
    )
    return CajaGateResponse(hay_caja_abierta=bool(turno_hoy_abierto))


@router.get("/caja/estado", response_model=CajaEstadoResponse)
def obtener_estado_caja(
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
    tz_offset: int = Depends(get_tz_offset),
):
    validar_admin(db, usuario_actual, cliente_id)
    _auto_cerrar_si_vencida(db, cliente_id, tz_offset)

    hoy = _hoy_local(tz_offset)

    # Como máximo un turno abierto a la vez (ver abrir_caja) — no hace
    # falta filtrar por fecha acá.
    caja_abierta = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado == "abierto")
        .first()
    )

    turnos_hoy_query = db.query(CierreCaja).filter(
        CierreCaja.cliente_id == cliente_id, CierreCaja.fecha == hoy.isoformat()
    )
    turnos_hoy = turnos_hoy_query.count()

    # El turno cerrado más reciente de hoy (si hay varios, el último) — solo
    # como confirmación rápida en pantalla; el historial completo lista todos.
    ultimo_cierre_hoy = None
    if not caja_abierta:
        ultimo_cierre_hoy = (
            turnos_hoy_query
            .filter(CierreCaja.estado != "abierto")
            .order_by(CierreCaja.cerrado_en.desc())
            .first()
        )

    ventas_hasta_ahora = 0.0
    gastos_hasta_ahora = 0.0
    es_atrasada = False
    if caja_abierta:
        fecha_caja = date.fromisoformat(caja_abierta.fecha)
        es_atrasada = fecha_caja != hoy
        ventas_hasta_ahora, gastos_hasta_ahora = _calcular_ventas_gastos_periodo(
            db, cliente_id, caja_abierta.abierto_en, datetime.utcnow()
        )

    return CajaEstadoResponse(
        hay_caja_abierta=bool(caja_abierta),
        caja_abierta=caja_abierta,
        es_atrasada=es_atrasada,
        ventas_hasta_ahora=ventas_hasta_ahora,
        gastos_hasta_ahora=gastos_hasta_ahora,
        ultimo_cierre_hoy=ultimo_cierre_hoy,
        turnos_hoy=turnos_hoy,
    )


@router.post("/caja/abrir", response_model=CierreCajaResponse, status_code=201)
def abrir_caja(
    payload: AbrirCajaRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
    tz_offset: int = Depends(get_tz_offset),
):
    validar_admin(db, usuario_actual, cliente_id)
    _auto_cerrar_si_vencida(db, cliente_id, tz_offset)

    # Único requisito para abrir: que no haya YA un turno abierto (de hoy o
    # de un día anterior — aunque a esta altura _auto_cerrar_si_vencida ya
    # habrá resuelto cualquiera de un día anterior). Un turno cerrado, sea
    # de hoy o de ayer, nunca bloquea abrir uno nuevo.
    ya_abierta = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado == "abierto")
        .first()
    )
    if ya_abierta:
        raise HTTPException(status_code=400, detail="Ya hay un turno de caja abierto. Ciérralo antes de abrir otro.")

    hoy = _hoy_local(tz_offset)
    caja = CierreCaja(
        cliente_id=cliente_id,
        fecha=hoy.isoformat(),
        saldo_inicial=payload.saldo_inicial,
        abierto_en=datetime.utcnow(),
        abierto_por=usuario_actual,
        estado="abierto",
    )
    db.add(caja)
    db.commit()
    db.refresh(caja)

    registrar_evento(
        db, actor=usuario_actual, accion="abrir_caja", entidad="cierre_caja",
        entidad_id=caja.id, cliente_id=cliente_id, detalle=f"saldo_inicial: {payload.saldo_inicial}",
    )

    return caja


@router.post("/caja/cerrar", response_model=CierreCajaResponse)
def cerrar_caja(
    payload: CerrarCajaRequest,
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario_actual, cliente_id)

    # Cierra el turno que esté abierto (a lo mucho uno), sea de hoy o
    # atrasado — nunca se filtra por fecha=hoy: si se olvidó cerrar ayer,
    # es ese turno el que hay que cerrar.
    caja = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado == "abierto")
        .first()
    )
    if not caja:
        raise HTTPException(status_code=400, detail="No hay ningún turno de caja abierto. Ábrelo primero.")

    ahora = datetime.utcnow()
    ventas, gastos = _calcular_ventas_gastos_periodo(db, cliente_id, caja.abierto_en, ahora)

    saldo_esperado = round(caja.saldo_inicial + ventas - gastos - payload.retiros_personales, 2)
    diferencia = round(payload.saldo_contado - saldo_esperado, 2)
    variacion_pct = round((diferencia / saldo_esperado * 100), 2) if saldo_esperado else 0.0

    caja.ventas_cobradas = ventas
    caja.gastos_efectivo = gastos
    caja.retiros_personales = payload.retiros_personales
    caja.saldo_esperado = saldo_esperado
    caja.saldo_contado = payload.saldo_contado
    caja.diferencia = diferencia
    caja.variacion_pct = variacion_pct
    caja.razon_discrepancia = payload.razon_discrepancia
    caja.cerrado_en = ahora
    caja.cerrado_por = usuario_actual
    caja.estado = _clasificar_estado(diferencia)

    db.commit()
    db.refresh(caja)

    registrar_evento(
        db, actor=usuario_actual, accion="cerrar_caja", entidad="cierre_caja",
        entidad_id=caja.id, cliente_id=cliente_id,
        detalle=f"esperado: {saldo_esperado}, contado: {payload.saldo_contado}, diferencia: {diferencia}",
    )

    return caja


@router.get("/caja/historial", response_model=list[CierreCajaResponse])
def historial_caja(
    limit: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
    usuario_actual: str = Depends(get_usuario_actual),
):
    validar_admin(db, usuario_actual, cliente_id)

    return (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado != "abierto")
        # Con varios turnos el mismo día, ordenar solo por fecha no alcanza
        # para dejarlos más-reciente-primero — cerrado_en como desempate.
        .order_by(CierreCaja.fecha.desc(), CierreCaja.cerrado_en.desc())
        .limit(limit)
        .all()
    )
