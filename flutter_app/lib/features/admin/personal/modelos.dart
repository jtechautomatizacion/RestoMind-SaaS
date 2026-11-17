import 'package:flutter/foundation.dart';

import '../../../core/roles.dart';

/// Una cuenta del restaurante tal como la devuelve GET /usuarios
/// (UsuarioResponse). Incluye al propio admin.
@immutable
class Miembro {
  const Miembro({
    required this.id,
    required this.nombre,
    required this.rol,
    required this.roles,
    required this.estado,
    this.email,
    this.celular,
  });

  factory Miembro.desdeJson(Map<String, dynamic> j) => Miembro(
    id: j['id'] as String,
    nombre: j['nombre'] as String? ?? '',
    email: j['email'] as String?,
    celular: j['celular'] as String?,
    rol: j['rol'] as String? ?? '',
    roles: [for (final r in j['roles'] as List<dynamic>? ?? const []) '$r'],
    estado: j['estado'] as String? ?? 'activo',
  );

  final String id;
  final String nombre;

  /// Solo el admin tiene email: el personal entra con su código de acceso.
  final String? email;

  /// El código de acceso de 6 dígitos que generó el backend. La columna se
  /// sigue llamando `celular` para no forzar una migración, pero ya no es un
  /// número de teléfono.
  final String? celular;
  final String rol;
  final List<String> roles;
  final String estado;

  bool get esAdmin => rol == 'admin';
  bool get activo => estado != 'inactivo';

  /// Con qué entra: el email del admin o el código del personal.
  String get acceso => email ?? celular ?? '';

  String get etiquetaRoles => roles.map((r) => etiquetaRol[r] ?? r).join(' + ');
}

/// Los roles que se ofrecen al crear o editar personal, en el orden en que se
/// ven. Nunca 'admin': ese lo da de alta el superadmin al registrar el
/// restaurante, y el backend rechaza crearlo o ascender a alguien (403).
const rolesPersonal = ['mozo', 'cajero', 'jefe_cocina', 'asistente'];

/// Roles que no se combinan con ningún otro (ROLES_EXCLUSIVOS en
/// backend/utils/roles.py). 'asistente' ya cubre mesas, cocina y cobro.
const rolesExclusivos = {'asistente'};

/// ¿Ese rol queda bloqueado con lo que ya está marcado? El backend lo
/// rechazaría con un 422; se bloquea en el momento para que el estado
/// imposible no llegue a existir en pantalla.
bool rolBloqueado(String rol, Set<String> marcados) {
  final hayExclusivo = marcados.any(rolesExclusivos.contains);
  final esExclusivo = rolesExclusivos.contains(rol);
  return hayExclusivo ? !esExclusivo : esExclusivo && marcados.isNotEmpty;
}
