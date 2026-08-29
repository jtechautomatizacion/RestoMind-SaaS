"""
CU-05: Dashboard Financiero
Serie de ventas/gastos/ganancia por día + top platos, para alimentar
los gráficos del panel de administración ("cómo viaja mi dinero").

Las ventas se cuentan cuando la comanda pasa a estado 'cobrado'
(dinero realmente cobrado), no cuando se crea la comanda.
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.dependencies import get_cliente_id
from backend.models import Comanda, ComandaPlato, Compra
from backend.schemas import DashboardResumen, DashboardSerieItem, DashboardTotales, TopPlatoItem

router = APIRouter()


@router.get("/dashboard/resumen", response_model=DashboardResumen)
def resumen_financiero(
    dias: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
    cliente_id: str = Depends(get_cliente_id),
):
    # Se usa la fecha UTC (no la local) porque todos los timestamps de la BD
    # (creado_en, actualizado_en) se guardan con datetime.utcnow(). Mezclar
    # date.today() (local) con esos timestamps hacía que ventas cercanas a
    # medianoche "desaparecieran" del rango en zonas horarias como Perú (UTC-5).
    hoy = datetime.utcnow().date()
    inicio = hoy - timedelta(days=dias - 1)
    inicio_dt = datetime.combine(inicio, datetime.min.time())

    comandas_cobradas = (
        db.query(Comanda)
        .filter(
            Comanda.cliente_id == cliente_id,
            Comanda.estado == "cobrado",
            Comanda.actualizado_en >= inicio_dt,
        )
        .all()
    )

    compras_periodo = (
        db.query(Compra)
        .filter(
            Compra.cliente_id == cliente_id,
            Compra.estado == "registrado",
            Compra.fecha >= inicio.isoformat(),
            Compra.fecha <= hoy.isoformat(),
        )
        .all()
    )

    ventas_por_dia: dict = {}
    comandas_por_dia: dict = {}
    for c in comandas_cobradas:
        fecha_str = c.actualizado_en.date().isoformat()
        ventas_por_dia[fecha_str] = ventas_por_dia.get(fecha_str, 0.0) + c.total_cuenta
        comandas_por_dia[fecha_str] = comandas_por_dia.get(fecha_str, 0) + 1

    gastos_por_dia: dict = {}
    for compra in compras_periodo:
        gastos_por_dia[compra.fecha] = gastos_por_dia.get(compra.fecha, 0.0) + compra.monto

    serie = []
    for i in range(dias):
        fecha_str = (inicio + timedelta(days=i)).isoformat()
        ventas = round(ventas_por_dia.get(fecha_str, 0.0), 2)
        gastos = round(gastos_por_dia.get(fecha_str, 0.0), 2)
        serie.append(DashboardSerieItem(
            fecha=fecha_str,
            ventas=ventas,
            gastos=gastos,
            ganancia=round(ventas - gastos, 2),
            comandas=comandas_por_dia.get(fecha_str, 0),
        ))

    totales = DashboardTotales(
        ventas=round(sum(item.ventas for item in serie), 2),
        gastos=round(sum(item.gastos for item in serie), 2),
        ganancia=round(sum(item.ganancia for item in serie), 2),
        comandas=sum(item.comandas for item in serie),
    )

    top_platos_map: dict = {}
    if comandas_cobradas:
        ids_comandas = [c.id for c in comandas_cobradas]
        detalle = db.query(ComandaPlato).filter(ComandaPlato.comanda_id.in_(ids_comandas)).all()
        for cp in detalle:
            nombre = cp.plato.nombre if cp.plato else "Plato eliminado"
            acumulado = top_platos_map.setdefault(nombre, {"cantidad": 0, "revenue": 0.0})
            acumulado["cantidad"] += cp.cantidad
            acumulado["revenue"] += cp.subtotal

    top_platos = sorted(
        (TopPlatoItem(nombre=n, cantidad=v["cantidad"], revenue=round(v["revenue"], 2)) for n, v in top_platos_map.items()),
        key=lambda item: item.revenue,
        reverse=True,
    )[:5]

    return DashboardResumen(periodo_dias=dias, serie=serie, totales=totales, top_platos=top_platos)
