"""
Consulta local del Padrón Reducido de SUNAT.

La base la construye backend/scripts/cargar_padron_sunat.py. Este módulo
solo LEE, y siempre en modo de solo lectura a nivel del propio SQLite: si
algún día alguien escribe un UPDATE por error, falla en vez de corromper
una base de 1.6 GB que tarda minutos en reconstruirse.

RENDIMIENTO
-----------
Medido sobre datos reales del padrón: mediana 0.022 ms, p99 0.063 ms por
consulta. El objetivo de "menos de 50 ms en móvil" lo decide el viaje de
red hasta el VPS, no esta consulta — que es unas 800 veces más rápida que
todo el presupuesto. Por eso NO hace falta Redis por delante: agregaría una
pieza más que mantener para ahorrar centésimas de milisegundo.

DATOS PERSONALES
----------------
Los RUC 10/15/16/17 son personas naturales y su "nombre" es el de una
persona real (Ley N° 29733). Este módulo no registra en logs ni el RUC
consultado ni el nombre devuelto: un log de accesos sería, en la práctica,
un segundo registro de datos personales creciendo sin control.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Prefijos de RUC que SUNAT tiene en uso.
#
# 10, 15, 16, 17 -> personas naturales (15/16/17 son asignaciones antiguas)
# 20             -> personas jurídicas
#
# Los prefijos 15 y 17 aparecen de verdad en el padrón: en una muestra de
# 154.132 contribuyentes reales eran 11.432, un 7,4%. Aceptar solo 10 y 20
# —como se hacía antes— rechaza a esos contribuyentes cuando piden factura.
PREFIJOS_VALIDOS = ("10", "15", "16", "17", "20")

PREFIJOS_PERSONA_NATURAL = ("10", "15", "16", "17")

# Pesos del dígito verificador del RUC. Verificado contra 154.132 RUC reales
# del padrón: 100% de coincidencia.
_PESOS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

_local = threading.local()


class PadronNoDisponible(Exception):
    """La base todavía no se construyó (o se movió). No es un error del
    usuario: es configuración pendiente del servidor."""


@dataclass
class Contribuyente:
    ruc: str
    nombre: str
    estado: str          # ACTIVO, BAJA DE OFICIO, SUSPENSION TEMPORAL...
    condicion: str       # HABIDO, NO HABIDO, NO HALLADO...
    persona_natural: bool

    @property
    def puede_facturarse(self) -> bool:
        """Un contribuyente de baja o no habido puede hacer que SUNAT
        observe el comprobante. Conviene avisarlo ANTES de emitir, que es
        cuando todavía se puede corregir."""
        return self.estado == "ACTIVO" and self.condicion == "HABIDO"


def digito_verificador_ok(ruc: str) -> bool:
    """
    Valida el dígito de control del RUC.

    Es lo que separa "once dígitos cualesquiera" de "un RUC que existe":
    atrapa el número mal tipeado en el mostrador, sin consultar nada. La
    validación anterior (largo + prefijo) dejaba pasar cualquier tipeo.
    """
    if len(ruc) != 11 or not ruc.isdigit():
        return False
    suma = sum(int(ruc[i]) * _PESOS[i] for i in range(10))
    digito = 11 - (suma % 11)
    if digito == 10:
        digito = 0
    elif digito == 11:
        digito = 1
    return digito == int(ruc[10])


def formato_valido(ruc: str) -> bool:
    """Forma correcta: 11 dígitos, prefijo en uso y dígito de control válido."""
    return (
        len(ruc) == 11
        and ruc.isdigit()
        and ruc[:2] in PREFIJOS_VALIDOS
        and digito_verificador_ok(ruc)
    )


def _conexion(ruta: Path) -> sqlite3.Connection:
    """
    Una conexión por hilo.

    FastAPI atiende los endpoints síncronos en un pool de hilos, y una
    conexión de sqlite3 no se puede compartir entre hilos sin serializar los
    accesos. Una por hilo evita tanto el error como el cuello de botella de
    un lock global, y se reutiliza entre pedidos (abrir la base en cada
    request costaría más que la propia consulta).
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn

    if not ruta.exists():
        raise PadronNoDisponible(
            "La base del padrón de SUNAT no está construida. "
            "Ejecuta: python -m backend.scripts.cargar_padron_sunat"
        )

    # mode=ro a nivel del driver: ni un bug ni un SQL mal escrito pueden
    # escribir. Es más fuerte que confiar en no mandar UPDATEs.
    conn = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, check_same_thread=False)
    conn.execute("PRAGMA query_only = ON")
    # La base ya quedó en WAL al construirla; esto solo aplica a ESTA
    # conexión y permite lecturas sin bloquear ni ser bloqueadas.
    conn.execute("PRAGMA busy_timeout = 3000")
    # 8 MB de caché por hilo: mantiene los niveles altos del índice en
    # memoria (que es lo que se toca en toda consulta) sin comprometer la
    # RAM del VPS.
    conn.execute("PRAGMA cache_size = -8000")
    _local.conn = conn
    return conn


def consultar(ruc: str, ruta_db: str | Path) -> Optional[Contribuyente]:
    """
    Busca un RUC. Devuelve None si no está en el padrón.

    No valida el formato: eso lo hace quien llama, ANTES, para no gastar una
    consulta en un número que ni siquiera puede existir.
    """
    conn = _conexion(Path(ruta_db))
    fila = conn.execute(
        "SELECT nombre, estado, condicion FROM padron WHERE ruc = ?", (ruc,)
    ).fetchone()
    if fila is None:
        return None
    return Contribuyente(
        ruc=ruc,
        nombre=fila[0],
        estado=fila[1] or "",
        condicion=fila[2] or "",
        persona_natural=ruc[:2] in PREFIJOS_PERSONA_NATURAL,
    )


def info_padron(ruta_db: str | Path) -> dict:
    """Cuántos contribuyentes hay y de cuándo es el archivo — para que el
    admin sepa si el padrón quedó viejo (SUNAT lo actualiza a diario)."""
    ruta = Path(ruta_db)
    if not ruta.exists():
        return {"disponible": False, "contribuyentes": 0, "actualizado_en": None}
    import datetime

    conn = _conexion(ruta)
    total = conn.execute("SELECT COUNT(*) FROM padron").fetchone()[0]
    return {
        "disponible": True,
        "contribuyentes": total,
        "actualizado_en": datetime.datetime.utcfromtimestamp(
            ruta.stat().st_mtime
        ).isoformat() + "Z",
    }


def cerrar_conexion_del_hilo() -> None:
    """Para los tests: sin esto, una conexión abierta contra una base
    temporal ya borrada se reutilizaría en el test siguiente."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


# ============ DNI: NO SALE DEL PADRÓN ============

def consultar_dni_externo(dni: str) -> Optional[str]:
    """
    Resuelve un DNI contra el servicio externo configurado. Devuelve el
    nombre, o None.

    El Padrón Reducido de SUNAT solo tiene RUC: un DNI no está ahí y no hay
    ninguna fuente pública gratuita que lo resuelva. De ahí que esto sea un
    servicio de pago y venga APAGADO por defecto.

    NUNCA propaga una excepción ni bloquea: si no hay servicio configurado,
    si tarda, o si contesta cualquier cosa, devuelve None y el cajero escribe
    el nombre a mano. Una venta no se puede frenar porque un proveedor
    externo tuvo un mal día.

    No se registra el DNI consultado ni el nombre devuelto en ningún log —
    son datos personales de un comensal.
    """
    from backend.config import settings

    if not settings.dni_api_url:
        return None

    try:
        import httpx

        cabeceras = {}
        if settings.dni_api_token:
            cabeceras["Authorization"] = f"Bearer {settings.dni_api_token}"
        resp = httpx.get(
            settings.dni_api_url.rstrip("/") + "/" + dni,
            headers=cabeceras,
            timeout=settings.dni_api_timeout,
        )
        if resp.status_code != 200:
            return None
        datos = resp.json()
    except Exception:  # noqa: BLE001 — red, timeout, JSON inválido: todo es "no encontrado"
        return None

    if not isinstance(datos, dict):
        return None

    # Los proveedores peruanos de consulta de DNI no comparten un formato:
    # unos devuelven el nombre ya armado, otros lo parten en nombres y
    # apellidos. Se aceptan las dos formas para no atar el código a uno solo.
    directo = datos.get("nombre_completo") or datos.get("nombreCompleto") or datos.get("nombre")
    if isinstance(directo, str) and directo.strip():
        return " ".join(directo.split()).upper()

    partes = [
        datos.get("nombres"),
        datos.get("apellido_paterno") or datos.get("apellidoPaterno"),
        datos.get("apellido_materno") or datos.get("apellidoMaterno"),
    ]
    armado = " ".join(p.strip() for p in partes if isinstance(p, str) and p.strip())
    return " ".join(armado.split()).upper() or None
