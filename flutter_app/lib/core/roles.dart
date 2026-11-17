/// Roles y pestañas. ESPEJO de backend/utils/roles.py: si cambia uno, cambia el
/// otro. Esto solo decide qué se MUESTRA; quién puede qué lo decide siempre el
/// backend en cada llamada (un 403 de la API manda sobre cualquier cosa de acá).
library;

enum Pestana { mesas, cocina, dinero, admin }

const Map<String, Set<Pestana>> pestanasPorRol = {
  'admin': {Pestana.mesas, Pestana.cocina, Pestana.dinero, Pestana.admin},
  'mozo': {Pestana.mesas},
  'cajero': {Pestana.mesas},
  'jefe_cocina': {Pestana.cocina},
  // Cubre las tres estaciones, SIN Dinero ni Administración: es personal de
  // confianza que atiende solo, no el dueño.
  'asistente': {Pestana.mesas, Pestana.cocina},
};

const Map<String, String> etiquetaRol = {
  'admin': 'Admin',
  'mozo': 'Mozo',
  'cajero': 'Cajero',
  'jefe_cocina': 'Cocina',
  'asistente': 'Asistente',
};

/// Quién opera en "Atiendo solo" (Vista Unificada). Lista EXPLÍCITA, no una
/// regla derivada: un mozo, un cajero y un cocinero trabajan en paralelo y se
/// pisarían cobrando la misma mesa desde dos vistas de tres columnas.
const Set<String> rolesVistaUnificada = {'admin', 'asistente'};

/// Pestañas visibles: la UNIÓN de las de todos los roles de la cuenta, en el
/// orden de la barra de navegación.
List<Pestana> pestanasDe(Iterable<String> roles) {
  final set = <Pestana>{for (final r in roles) ...?pestanasPorRol[r]};
  return Pestana.values.where(set.contains).toList();
}

bool veVistaUnificada(Iterable<String> roles) =>
    roles.any(rolesVistaUnificada.contains);

/// "Solo cobra": una cuenta de cajero SIN mozo ni admin ve Mesas para cobrar,
/// no para tomar pedidos (que no confunda una cosa con la otra). Con cajero y
/// mozo a la vez sí toma pedidos: la restricción es del cajero en solitario.
bool soloCobra(Iterable<String> roles) =>
    roles.contains('cajero') &&
    !roles.contains('mozo') &&
    !roles.contains('admin');
