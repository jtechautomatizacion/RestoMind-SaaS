"""
Roles combinables de personal, guardados como CSV en Usuario.rol.

`admin` siempre vive solo (nunca combinado): todo el código de seguridad
que ya compara `usuario.rol == "admin"` / `!= "admin"` (validar_admin,
los guards de ascenso en routes/usuarios.py, las queries "buscar el admin
del restaurante" en superadmin.py/seed.py) sigue funcionando sin tocarlo,
porque ese valor nunca lleva coma.

Para staff, la columna guarda una lista separada por comas de
{mozo, cajero, jefe_cocina} — ej. "cajero,jefe_cocina" — para que una
sola cuenta pueda cubrir varias tareas cuando el restaurante tiene poco
personal (el caso real: una sola persona hace cocina Y cobra). Los datos
existentes de un solo rol ("mozo") siguen siendo válidos sin migración:
roles_de("mozo") == ["mozo"].
"""

ROLES_STAFF = ("mozo", "cajero", "jefe_cocina")


def roles_de(valor_rol: str) -> list:
    """CSV guardado en BD -> lista de roles. 'admin' devuelve ['admin']."""
    if not valor_rol:
        return []
    return valor_rol.split(",")


def tiene_rol(valor_rol: str, rol: str) -> bool:
    return rol in roles_de(valor_rol)


def serializar_roles(roles: list) -> str:
    return ",".join(roles)
