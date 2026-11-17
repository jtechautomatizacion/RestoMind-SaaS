import '../../../core/api/api_client.dart';
import 'modelos.dart';

/// Cuentas del restaurante. Todo es admin-only en el backend.
class PersonalRepo {
  const PersonalRepo(this._api);

  final ApiClient _api;

  Future<List<Miembro>> listar() async {
    final lista = await _api.get('/usuarios') as List<dynamic>;
    return [
      for (final j in lista) Miembro.desdeJson(j as Map<String, dynamic>),
    ];
  }

  /// El código de acceso NO se manda: lo genera el backend y vuelve en
  /// `celular` de la respuesta.
  Future<Miembro> crear({
    required String nombre,
    required String password,
    required List<String> roles,
  }) async {
    final j = await _api.post('/usuarios/staff', {
      'nombre': nombre,
      'password': password,
      'roles': roles,
    });
    return Miembro.desdeJson(j as Map<String, dynamic>);
  }

  /// Los campos nulos no viajan: los roles de un admin, por ejemplo, nunca se
  /// mandan porque el backend los rechazaría.
  Future<void> editar(
    String id, {
    required String nombre,
    List<String>? roles,
    bool? activo,
  }) => _api.patch('/usuarios/$id', {
    'nombre': nombre,
    'roles': ?roles,
    if (activo != null) 'estado': activo ? 'activo' : 'inactivo',
  });

  Future<void> resetearPassword(String id, String nueva) =>
      _api.patch('/usuarios/$id/password', {'nueva_password': nueva});

  Future<void> eliminar(String id) => _api.delete('/usuarios/$id');
}
