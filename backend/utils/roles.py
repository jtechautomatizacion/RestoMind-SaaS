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

'asistente' es un cuarto rol de staff que NO se combina: ver ROL_ASISTENTE
más abajo.
"""

# 'asistente' cubre las tres estaciones (mesas, cocina, cobro) en una sola
# persona. No es azúcar sintáctico sobre "mozo,cajero,jefe_cocina": es la
# cuenta de quien atiende SOLO, y es —junto con admin— la única a la que se
# le ofrece la Vista Unificada ("Todo en uno").
#
# Esa distinción es el motivo de que exista. Un mozo, un cajero y un
# cocinero trabajan en PARALELO sobre la misma sala: cada uno necesita su
# pantalla enfocada en su tarea, y meterlos a todos en una vista de tres
# columnas los haría pisarse (dos personas cobrando la misma mesa desde
# dos "Todo en uno" distintos). El asistente es el caso contrario: no hay
# con quién pisarse.
ROL_ASISTENTE = "asistente"

ROLES_STAFF = ("mozo", "cajero", "jefe_cocina", ROL_ASISTENTE)

# Roles que NO se combinan con ningún otro. 'asistente' ya cubre todo lo que
# cubren los demás, así que "asistente,mozo" no agrega nada y sí crea una
# cuenta ambigua: ¿le toca la vista de uno o la del otro? Se rechaza en la
# validación en vez de resolverse con una regla de desempate que nadie
# recuerde después. ('admin' no está acá porque nunca pasa por este camino:
# lo asigna el superadmin al crear el restaurante.)
ROLES_EXCLUSIVOS = (ROL_ASISTENTE,)

# Quién ve la Vista Unificada ("Todo en uno"). Es una LISTA EXPLÍCITA de
# roles a propósito, no una regla derivada de "¿ve Mesas y ve Cocina?" como
# antes: con la regla derivada, una cuenta 'cajero,jefe_cocina' —que existe
# para que UNA persona cubra dos estaciones mientras OTRAS trabajan la
# sala— caía adentro sin que nadie lo hubiera decidido.
ROLES_VISTA_UNIFICADA = ("admin", ROL_ASISTENTE)


def ve_vista_unificada(valor_rol: str) -> bool:
    """¿Esta cuenta opera en modo 'Todo en uno'?"""
    return any(r in ROLES_VISTA_UNIFICADA for r in roles_de(valor_rol))


def roles_de(valor_rol: str) -> list:
    """CSV guardado en BD -> lista de roles. 'admin' devuelve ['admin']."""
    if not valor_rol:
        return []
    return valor_rol.split(",")


def tiene_rol(valor_rol: str, rol: str) -> bool:
    return rol in roles_de(valor_rol)


def serializar_roles(roles: list) -> str:
    return ",".join(roles)
