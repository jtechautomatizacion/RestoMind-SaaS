"""
Genera el token que usa el agente de la PC del restaurante para bajar los
comprobantes SUNAT (ver backend/routes/agente.py).

Lo corre el dueño del sistema por SSH al dar de alta un restaurante, una
sola vez. El restaurante nunca ve este script: solo recibe el token para
pegarlo en el config.json del agente.

Uso:
    python -m backend.scripts.crear_token_agente <cliente_id> ["Nombre de la caja"]
    python -m backend.scripts.crear_token_agente --listar <cliente_id>
    python -m backend.scripts.crear_token_agente --revocar <token_id>

EL TOKEN SE MUESTRA UNA SOLA VEZ. Se guarda hasheado con bcrypt, igual que
una contraseña, porque va a vivir en el disco de una PC que está en el
salón de un local: hay que poder revocarlo, pero no hay ninguna razón para
poder volver a leerlo. Si se pierde, se genera otro y se revoca el viejo.
"""

import secrets
import sys

from backend.auth import hash_password
from backend.database import SessionLocal
from backend.models import AgenteToken, Cliente


def _crear(cliente_id: str, nombre: str) -> int:
    db = SessionLocal()
    try:
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if not cliente:
            print(f"ERROR: no existe un restaurante con id '{cliente_id}'.")
            print("       Listá los existentes con: python -m backend.scripts.crear_cliente --listar")
            return 1

        if not cliente.ruc:
            # No es un error fatal —el token sirve igual— pero sin RUC no se
            # pueden emitir boletas, así que el agente no tendría nada que
            # bajar. Mejor avisarlo ahora que dejar al restaurante esperando.
            print(f"AVISO: '{cliente.nombre}' todavía no tiene RUC configurado.")
            print("       El agente va a funcionar, pero no habrá comprobantes que entregar")
            print("       hasta que se cargue el RUC desde el Panel General.")

        # token_urlsafe(32) da 43 caracteres de entropía criptográfica: no
        # es adivinable ni por fuerza bruta, y entra en una línea de JSON
        # sin escapes raros.
        token = secrets.token_urlsafe(32)

        db.add(AgenteToken(
            cliente_id=cliente_id,
            nombre=nombre,
            token_hash=hash_password(token),
        ))
        db.commit()

        print()
        print("=" * 68)
        print(f"  Token del agente para: {cliente.nombre}")
        print(f"  Caja: {nombre}")
        print("=" * 68)
        print()
        print(f"  {token}")
        print()
        print("  ESTE TOKEN NO SE PUEDE VOLVER A VER. Copialo ahora.")
        print("  Va en el config.json del agente, en el campo \"token\".")
        print("=" * 68)
        return 0
    finally:
        db.close()


def _listar(cliente_id: str) -> int:
    db = SessionLocal()
    try:
        tokens = (
            db.query(AgenteToken)
            .filter(AgenteToken.cliente_id == cliente_id)
            .order_by(AgenteToken.creado_en.desc())
            .all()
        )
        if not tokens:
            print(f"No hay tokens de agente para '{cliente_id}'.")
            return 0

        print(f"{'ID':>4}  {'ESTADO':<9} {'CAJA':<24} {'ÚLTIMO USO':<20} CREADO")
        for t in tokens:
            # "último uso" es lo que dice si un agente sigue vivo: un
            # restaurante que hace días no reporta tiene la PC apagada, sin
            # internet, o la tarea programada borrada.
            ultimo = t.ultimo_uso_en.strftime("%Y-%m-%d %H:%M UTC") if t.ultimo_uso_en else "nunca"
            creado = t.creado_en.strftime("%Y-%m-%d") if t.creado_en else "?"
            print(f"{t.id:>4}  {t.estado:<9} {t.nombre[:24]:<24} {ultimo:<20} {creado}")
        return 0
    finally:
        db.close()


def _revocar(token_id: int) -> int:
    db = SessionLocal()
    try:
        token = db.query(AgenteToken).filter(AgenteToken.id == token_id).first()
        if not token:
            print(f"ERROR: no existe un token con id {token_id}.")
            return 1
        # Se marca revocado en vez de borrarlo: así queda el rastro de que
        # ese agente existió y cuándo se usó por última vez.
        token.estado = "revocado"
        db.commit()
        print(f"Token {token_id} ('{token.nombre}') revocado. Deja de funcionar en el próximo request.")
        return 0
    finally:
        db.close()


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1

    if args[0] == "--listar":
        if len(args) < 2:
            print("Uso: python -m backend.scripts.crear_token_agente --listar <cliente_id>")
            return 1
        return _listar(args[1])

    if args[0] == "--revocar":
        if len(args) < 2 or not args[1].isdigit():
            print("Uso: python -m backend.scripts.crear_token_agente --revocar <token_id>")
            return 1
        return _revocar(int(args[1]))

    cliente_id = args[0]
    nombre = args[1] if len(args) > 1 else "Caja principal"
    return _crear(cliente_id, nombre)


if __name__ == "__main__":
    sys.exit(main())
