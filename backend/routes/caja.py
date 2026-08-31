"""
Validador de Caja — apertura/cierre diario, solo admin.

Flujo (ver CierreCaja en models.py para el porqué de dos pasos separados):
  1. POST /caja/abrir   (mañana) — declara saldo_inicial
  2. ...   el día opera normal (comandas, compras)  ...
  3. POST /caja/cerrar  (noche)  — declara saldo_contado; el sistema calcula
     ventas/gastos del día y la diferencia contra lo que "debería haber".

Solo puede existir UNA caja abierta a la vez por restaurante (lo impone
POST /caja/abrir): si el admin se olvida de cerrar un día, POST /caja/cerrar
sigue apuntando a ESA caja pendiente aunque ya no sea "hoy" — nunca se cierra
por accidente el día equivocado. Reabrir SIN cerrar la anterior está
bloqueado siempre — es obligatorio cerrar primero.

Válvula de seguridad — auto-cierre de caja vencida (_auto_cerrar_si_vencida):
Mesas y Cocina exigen una caja abierta HOY para operar (GET /caja/gate). Si
eso se combinara con un bloqueo estricto de "no se puede abrir sin cerrar la
anterior" y el admin genuinamente se olvidó una noche, el restaurante entero
quedaría congelado al día siguiente hasta que alguien lo note. Para evitar
ese bloqueo total, cualquier consulta a /caja/estado, /caja/gate o
/caja/abrir primero revisa si la caja abierta quedó de un día ANTERIOR al de
hoy; si es así, se cierra sola con saldo_contado = saldo_esperado (no hay
conteo físico real que usar) y queda marcada estado='cerrado_automatico'
—nunca 'cuadrado'— para que quede clarísimo en el historial que ese cierre
no fue validado por un conteo real y el admin debe revisarlo. Esto NO
relaja la regla "hay que cerrar para volver a abrir": simplemente el
sistema hace ese cierre pendiente por vos cuando ya pasó su día, en vez de
dejarlo trabado para siempre.

Ventas y gastos se calculan con el mismo criterio de zona horaria que el
dashboard (backend/routes/dashboard.py): los timestamps de la BD son UTC,
pero "el día" es el día LOCAL del restaurante — sin esto, una venta cobrada
a las 22:33 en Lima se cuenta en el día equivocado.
"""

from datetime import datetime, timedelta, date, time

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


def _rango_dia_local(fecha_local: date, tz_offset: int) -> tuple:
    desfase = timedelta(minutes=tz_offset)
    inicio_dt = datetime.combine(fecha_local, time.min) + desfase
    fin_dt = datetime.combine(fecha_local, time.max) + desfase
    return inicio_dt, fin_dt


def _calcular_ventas_gastos(db: Session, cliente_id: str, fecha_local: date, tz_offset: int) -> tuple:
    inicio_dt, fin_dt = _rango_dia_local(fecha_local, tz_offset)

    ventas = (
        db.query(Comanda)
        .filter(
            Comanda.cliente_id == cliente_id,
            Comanda.estado == "cobrado",
            Comanda.actualizado_en >= inicio_dt,
            Comanda.actualizado_en <= fin_dt,
        )
        .all()
    )
    total_ventas = round(sum(c.total_cuenta for c in ventas), 2)

    gastos = (
        db.query(Compra)
        .filter(
            Compra.cliente_id == cliente_id,
            Compra.estado == "registrado",
            Compra.fecha == fecha_local.isoformat(),
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
        return  # sigue siendo la caja de hoy — nada que auto-cerrar

    ventas, gastos = _calcular_ventas_gastos(db, cliente_id, fecha_caja, tz_offset)
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
        "Cierre automático: nadie cerró la caja antes de terminar el día "
        f"{caja.fecha}. No refleja un conteo físico real — revisar manualmente."
    )
    caja.cerrado_en = datetime.utcnow()
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
    Semáforo para Mesas/Cocina: ¿hay caja abierta HOY? Sin validar_admin a
    propósito — mozo/cocina también necesitan saber si pueden operar, y a
    diferencia de /caja/estado esta ruta nunca expone montos (eso es
    información financiera privada del admin, ver PRODUCTION_READINESS.md).
    """
    _auto_cerrar_si_vencida(db, cliente_id, tz_offset)

    hoy = _hoy_local(tz_offset)
    caja_hoy_abierta = (
        db.query(CierreCaja)
        .filter(
            CierreCaja.cliente_id == cliente_id,
            CierreCaja.estado == "abierto",
            CierreCaja.fecha == hoy.isoformat(),
        )
        .first()
    )
    return CajaGateResponse(hay_caja_abierta=bool(caja_hoy_abierta))


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

    # Como máximo una caja abierta a la vez (ver abrir_caja) — no hace
    # falta filtrar por fecha acá.
    caja_abierta = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado == "abierto")
        .first()
    )

    caja_cerrada_hoy = None
    if not caja_abierta:
        caja_cerrada_hoy = (
            db.query(CierreCaja)
            .filter(
                CierreCaja.cliente_id == cliente_id,
                CierreCaja.fecha == hoy.isoformat(),
                CierreCaja.estado != "abierto",
            )
            .first()
        )

    ventas_hasta_ahora = 0.0
    gastos_hasta_ahora = 0.0
    es_atrasada = False
    if caja_abierta:
        fecha_caja = date.fromisoformat(caja_abierta.fecha)
        es_atrasada = fecha_caja != hoy
        ventas_hasta_ahora, gastos_hasta_ahora = _calcular_ventas_gastos(db, cliente_id, fecha_caja, tz_offset)

    return CajaEstadoResponse(
        hay_caja_abierta=bool(caja_abierta),
        caja_abierta=caja_abierta,
        es_atrasada=es_atrasada,
        ventas_hasta_ahora=ventas_hasta_ahora,
        gastos_hasta_ahora=gastos_hasta_ahora,
        caja_cerrada_hoy=caja_cerrada_hoy,
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

    ya_abierta = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado == "abierto")
        .first()
    )
    if ya_abierta:
        hoy = _hoy_local(tz_offset)
        if ya_abierta.fecha != hoy.isoformat():
            raise HTTPException(
                status_code=400,
                detail=f"Tienes la caja del {ya_abierta.fecha} sin cerrar. Ciérrala antes de abrir una nueva.",
            )
        raise HTTPException(status_code=400, detail="Ya hay una caja abierta hoy.")

    hoy = _hoy_local(tz_offset)
    ya_cerrada_hoy = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.fecha == hoy.isoformat())
        .first()
    )
    if ya_cerrada_hoy:
        raise HTTPException(status_code=400, detail="La caja de hoy ya se cerró.")

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
    tz_offset: int = Depends(get_tz_offset),
):
    validar_admin(db, usuario_actual, cliente_id)

    # Cierra la que esté abierta (a lo mucho una), sea de hoy o atrasada —
    # nunca se filtra por fecha=hoy: si se olvidó cerrar ayer, es esa
    # caja la que hay que cerrar, no una de hoy que ni siquiera existe.
    caja = (
        db.query(CierreCaja)
        .filter(CierreCaja.cliente_id == cliente_id, CierreCaja.estado == "abierto")
        .first()
    )
    if not caja:
        raise HTTPException(status_code=400, detail="No hay ninguna caja abierta. Ábrela primero.")

    fecha_caja = date.fromisoformat(caja.fecha)
    ventas, gastos = _calcular_ventas_gastos(db, cliente_id, fecha_caja, tz_offset)

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
    caja.cerrado_en = datetime.utcnow()
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
        .order_by(CierreCaja.fecha.desc())
        .limit(limit)
        .all()
    )
