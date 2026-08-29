"""
CU-02 y CU-03: Gestión de Comandas
- CU-02: Registro y Envío de Comandas Express (Mozo)
- CU-03: Monitor de Cocina en Tiempo Real
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas import ComandaCreate, ComandaResponse, ComandaEstadoUpdate
from backend.models import Comanda

router = APIRouter()


# TODO: Implementar endpoints
# GET /api/comandas
# POST /api/comandas
# GET /api/comandas/{id}
# PATCH /api/comandas/{id}/estado
# GET /api/monitor/cocina (solo estado='cocina', ordenado por antigüedad)
