"""
Qué versión del APK es la vigente.

POR QUÉ HACE FALTA
------------------
RestoMind no se distribuye por una tienda, así que nada le avisa al
restaurante cuando sale una versión nueva: el APK se descarga de un enlace y
ahí se queda. Sin este endpoint, un local puede trabajar meses con una versión
vieja sin enterarse, y el primer síntoma sería un bug ya corregido reportado
como si fuera nuevo.

La app consulta esto al arrancar, compara contra su propio versionCode y
avisa. La decisión de actualizar es del restaurante — acá solo se informa.

POR QUÉ ES PÚBLICO
------------------
Se consulta ANTES de entrar, a propósito: si una versión vieja dejara de poder
iniciar sesión (un cambio en la API, por ejemplo), exigir sesión para preguntar
"¿hay una versión nueva?" dejaría al restaurante trabado sin ninguna pista.
Lo único que se expone es un número de versión y un enlace de descarga que ya
se le manda por correo a cada cliente al darlo de alta.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings

router = APIRouter()


class VersionAppResponse(BaseModel):
    version_code: int
    version_name: str
    url_descarga: str
    # El servidor NO decide si la actualización es obligatoria. Forzar a
    # actualizar en medio de un servicio —con mesas abiertas y gente
    # esperando— es peor que dejar correr una versión vieja un rato más.
    hay_publicada: bool


@router.get("/app/version", response_model=VersionAppResponse)
def version_publicada() -> VersionAppResponse:
    return VersionAppResponse(
        version_code=settings.apk_version_code,
        version_name=settings.apk_version_name,
        url_descarga=settings.apk_url,
        # Se exige AMBAS cosas: sin URL de descarga, avisar de una versión
        # nueva sería mandar al restaurante a buscar algo que no existe.
        hay_publicada=bool(settings.apk_version_code and settings.apk_url),
    )
