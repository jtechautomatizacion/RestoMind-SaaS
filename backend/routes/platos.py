"""
CU-01: Gestión de la Carta Inteligente
Endpoints para crear, actualizar y listar platos del menú.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas import PlatoCreate, PlatoResponse, PlatoUpdate
from backend.models import Plato

router = APIRouter()


# TODO: Implementar endpoints
# GET /api/platos
# POST /api/platos
# PATCH /api/platos/{id}
# PATCH /api/platos/{id}/estado
