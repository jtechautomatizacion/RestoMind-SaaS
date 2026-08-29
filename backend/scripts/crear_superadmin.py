"""
Crea TU cuenta de superadmin (el dueño del sistema) — se corre una sola
vez por servidor, a mano, la primera vez que se despliega.

No hay manera de crear una cuenta de superadmin desde la web a propósito:
si existiera un endpoint público para esto, cualquiera podría crearse su
propio acceso al panel que ve TODOS los restaurantes.

Uso:
    python -m backend.scripts.crear_superadmin
"""

import getpass
import sys

from backend.auth import hash_password
from backend.database import SessionLocal, init_db
from backend.models import SuperAdmin


def main() -> None:
    init_db()
    db = SessionLocal()

    try:
        print("=== Alta de cuenta de superadmin (panel general) ===\n")

        nombre = input("Tu nombre: ").strip()
        email = input("Tu email de login: ").strip().lower()

        if db.query(SuperAdmin).filter(SuperAdmin.email == email).first():
            print(f"\nYa existe un superadmin con el email '{email}'.")
            sys.exit(1)

        password = getpass.getpass("Contraseña (no se muestra al escribir): ")
        if len(password) < 6:
            print("La contraseña debe tener al menos 6 caracteres.")
            sys.exit(1)

        confirmacion = getpass.getpass("Confirma la contraseña: ")
        if password != confirmacion:
            print("Las contraseñas no coinciden.")
            sys.exit(1)

        db.add(SuperAdmin(
            id=f"super-{email.split('@')[0]}",
            nombre=nombre,
            email=email,
            password_hash=hash_password(password),
        ))
        db.commit()

        print(f"\n✅ Listo. Entra al panel general en:")
        print(f"   http://<tu-servidor>/static/superadmin.html")
        print(f"   Email: {email}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
