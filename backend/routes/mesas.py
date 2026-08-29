"""
Soporte: Gestión de Mesas
Endpoints para crear y consultar mesas.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas import MesaCreate, MesaResponse
from backend.models import Mesa

router = APIRouter()


# TODO: Implementar endpoints
# GET /api/mesas
# POST /api/mesas
# PATCH /api/mesas/{id}/estado
