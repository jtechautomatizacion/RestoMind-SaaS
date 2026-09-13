"""
Crea el restaurante de PRUEBAS para el ambiente BETA de SUNAT.

    python -m backend.scripts.crear_tenant_beta

POR QUÉ UN RESTAURANTE APARTE Y NO UN "MODO BETA"
-------------------------------------------------
El ambiente BETA de SUNAT no acepta el RUC ni el usuario SOL reales: exige
unas credenciales fijas y públicas, iguales para todo el mundo.

    RUC      20000000001
    Usuario  MODDATOS
    Clave    moddatos

RestoMind ata el certificado al RUC del restaurante y no deja cambiarlo (ver
routes/configuracion.py). Para probar contra BETA habría que aflojar esa
regla con un "si es beta, entonces..." — un condicional que vive para siempre
en el código de emisión y que algún día alguien va a activar sin querer en
producción.

Un restaurante de pruebas separado evita todo eso: mismo código, mismas
validaciones, sin una sola excepción. Y los datos reales quedan intactos.

QUÉ NO PASA ACÁ
---------------
No se crean el certificado ni las credenciales. Eso se hace por la pantalla
Admin > Boletas, a propósito: si se copian a mano, el flujo de activación
—que es el que va a usar cada restaurante nuevo— queda sin probar, y el
primer error aparece en producción con un cliente esperando.
"""

from __future__ import annotations

import sys

from backend.auth import hash_password
from backend.database import SessionLocal, init_db
from backend.models import Cliente, Usuario

# Credenciales públicas del ambiente BETA de SUNAT. No son un secreto: están
# en la documentación oficial y las usa todo el que desarrolla facturación
# electrónica en Perú.
RUC_BETA = "20000000001"
CLIENTE_ID = "rest-beta"
ADMIN_EMAIL = "beta@restomind.local"
ADMIN_PASSWORD = "beta12345"


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        existente = db.query(Cliente).filter(Cliente.id == CLIENTE_ID).first()
        if existente:
            print(f"[OK] El restaurante de pruebas '{CLIENTE_ID}' ya existe.")
            _resumen(existente)
            return

        cliente = Cliente(
            id=CLIENTE_ID,
            nombre="RestoMind BETA (pruebas)",
            email=ADMIN_EMAIL,
            ruc=RUC_BETA,
            razon_social="EMPRESA DE PRUEBAS SUNAT",
            direccion="AV. PRUEBAS 123 - LIMA",
            # Arranca apagado, como cualquier restaurante nuevo: se prende
            # cargando el certificado por la pantalla, que es justo el paso
            # que se quiere probar.
            usar_sunat=False,
            # BETA sí admite facturas, así que este tenant sirve para probar
            # LOS DOS caminos (B001 y F001) — que es algo que el restaurante
            # real, al ser Nuevo RUS, no puede ejercitar.
            emite_facturas=True,
        )
        db.add(cliente)

        db.add(Usuario(
            id=f"{CLIENTE_ID}-admin",
            cliente_id=CLIENTE_ID,
            nombre="Admin BETA",
            email=ADMIN_EMAIL,
            password_hash=hash_password(ADMIN_PASSWORD),
            rol="admin",
            estado="activo",
        ))
        db.commit()

        print(f"[OK] Restaurante de pruebas '{CLIENTE_ID}' creado.")
        _resumen(cliente)
    finally:
        db.close()


def _resumen(cliente: Cliente) -> None:
    print()
    print("  Entrá con:")
    print(f"    email    {ADMIN_EMAIL}")
    print(f"    clave    {ADMIN_PASSWORD}")
    print()
    print(f"  RUC del tenant : {cliente.ruc}")
    print(f"  Emite facturas : {'sí' if cliente.emite_facturas else 'no (solo boletas)'}")
    print(f"  Facturación    : {'activa' if cliente.usar_sunat else 'apagada (actívala cargando el certificado)'}")
    print()
    print("  Después, en Admin > Boletas, prendé el interruptor y cargá:")
    print("    Certificado   el .pfx de prueba (el demo de LLAMA.PE sirve)")
    print("    Usuario SOL   MODDATOS")
    print("    Clave SOL     moddatos")
    print()
    print("  Y en el .env del contenedor: SUNAT_MODE=beta")
    print("  BETA no emite comprobantes reales: nada de lo que mandes tiene")
    print("  efecto tributario.")


if __name__ == "__main__":
    sys.exit(main())
