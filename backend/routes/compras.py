"""
CU-04: Control de Compras y Caja Chica
Endpoints para registrar gastos diarios.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.schemas import CompraCreate, CompraResponse, CompraUpdate
from backend.models import Compra

router = APIRouter()


# TODO: Implementar endpoints
# GET /api/compras
# POST /api/compras
# PATCH /api/compras/{id}
# PATCH /api/compras/{id}/estado
