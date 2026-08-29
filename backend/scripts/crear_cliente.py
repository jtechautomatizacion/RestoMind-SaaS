"""
Onboarding manual de un restaurante nuevo — lo corre el dueño del sistema
(vía terminal, con acceso directo al servidor), no el restaurante.

No existe un endpoint público de registro a propósito: en el modelo de
reventa, cada tenant nuevo se da de alta a mano. El cliente final nunca ve
este script ni sabe que existe — solo recibe su URL, su email y su
contraseña para entrar a http://.../static/index.html.

Uso:
    python -m backend.scripts.crear_cliente

Pide los datos por consola de forma interactiva. Es idempotente respecto
al id del cliente: si ya existe un Cliente con ese id, no lo duplica y
avisa en vez de fallar con un error de base de datos poco claro.
"""

import getpass
import re
import sys

from backend.auth import hash_password
from backend.database import SessionLocal, init_db
from backend.models import Cliente, Mesa, Usuario


def _slug(texto: str) -> str:
    limpio = re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")
    return limpio or "restaurante"


def main() -> None:
    init_db()
    db = SessionLocal()

    try:
        print("=== Alta de nuevo restaurante (RestoMind) ===\n")

        nombre_restaurante = input("Nombre del restaurante: ").strip()
        if not nombre_restaurante:
            print("El nombre no puede estar vacío.")
            sys.exit(1)

        cliente_id = input(f"ID interno [{_slug(nombre_restaurante)}]: ").strip() or _slug(nombre_restaurante)

        if db.query(Cliente).filter(Cliente.id == cliente_id).first():
            print(f"\nYa existe un cliente con id '{cliente_id}'. Nada que hacer.")
            sys.exit(1)

        email_negocio = input("Email de contacto del restaurante: ").strip()
        telefono = input("Teléfono (opcional): ").strip() or None
        pais = input("País [Perú]: ").strip() or "Perú"
        moneda = input("Moneda [PEN]: ").strip() or "PEN"

        print("\n-- Cuenta del administrador (con la que el dueño entra al sistema) --")
        nombre_admin = input("Nombre del administrador: ").strip()
        email_admin = input("Email de login del administrador: ").strip().lower()
        password_admin = getpass.getpass("Contraseña (no se muestra al escribir): ")
        if len(password_admin) < 6:
            print("La contraseña debe tener al menos 6 caracteres.")
            sys.exit(1)

        if db.query(Usuario).filter(Usuario.email == email_admin).first():
            print(f"\nYa existe un usuario con el email '{email_admin}' (los emails son únicos en todo el sistema).")
            sys.exit(1)

        num_mesas = input("¿Cuántas mesas tiene? [8]: ").strip()
        num_mesas = int(num_mesas) if num_mesas.isdigit() else 8

        cliente = Cliente(
            id=cliente_id,
            nombre=nombre_restaurante,
            email=email_negocio,
            telefono=telefono,
            pais=pais,
            moneda=moneda,
        )
        db.add(cliente)

        db.add(Usuario(
            id=f"usr-admin-{cliente_id}",
            cliente_id=cliente_id,
            nombre=nombre_admin,
            email=email_admin,
            password_hash=hash_password(password_admin),
            rol="admin",
        ))

        for numero in range(1, num_mesas + 1):
            db.add(Mesa(cliente_id=cliente_id, numero=numero, capacidad=4))

        db.commit()

        print(f"\n✅ Listo. '{nombre_restaurante}' está dado de alta con {num_mesas} mesas.")
        print(f"   Pásale al dueño estas credenciales de acceso:")
        print(f"   Email:      {email_admin}")
        print(f"   Contraseña: (la que acabas de escribir)")
        print(f"   URL:        http://<tu-servidor>/static/index.html")

    finally:
        db.close()


if __name__ == "__main__":
    main()
