import '../../../core/api/api_client.dart';
import '../../../core/plataforma/plataforma.dart';
import 'modelos.dart';

/// Llamadas de Admin > Carta (backend/routes/platos.py y categorias.py).
class CartaRepo {
  const CartaRepo(this._api);
  final ApiClient _api;

  /// Sin `incluir_inactivos`: un plato que se "eliminó" pero quedó archivado
  /// por tener ventas tiene que desaparecer de la carta del admin igual que
  /// uno borrado de verdad.
  Future<DatosCarta> cargar() async {
    final (platos, categorias) = await (
      _api.get('/platos'),
      _api.get('/categorias'),
    ).wait;
    return DatosCarta(
      [
        for (final p in platos as List<dynamic>)
          Plato.desdeJson(p as Map<String, dynamic>),
      ],
      [
        for (final c in categorias as List<dynamic>)
          Categoria.desdeJson(c as Map<String, dynamic>),
      ],
    );
  }

  Future<Plato> crearPlato(BorradorPlato b) async => Plato.desdeJson(
    await _api.post('/platos', b.aJson()) as Map<String, dynamic>,
  );

  Future<Plato> editarPlato(int id, BorradorPlato b) async => Plato.desdeJson(
    await _api.patch('/platos/$id', b.aJson()) as Map<String, dynamic>,
  );

  /// Devuelve el mensaje del servidor: si el plato ya tiene ventas no se
  /// borra, se archiva, y el admin tiene que saber cuál de las dos pasó.
  Future<String> eliminarPlato(int id) async {
    final r = await _api.delete('/platos/$id');
    return r is Map && r['detail'] is String
        ? r['detail'] as String
        : 'Plato eliminado.';
  }

  /// El servidor recomprime siempre a JPEG de 800 px: no hace falta achicarla
  /// acá antes de subirla.
  Future<Plato> subirFoto(int id, ArchivoElegido archivo) async =>
      Plato.desdeJson(
        await _api.subirArchivo(
              '/platos/$id/imagen',
              campo: 'archivo',
              bytes: archivo.bytes,
              nombreArchivo: archivo.nombre,
            )
            as Map<String, dynamic>,
      );

  Future<void> quitarFoto(int id) => _api.delete('/platos/$id/imagen');

  Future<void> crearCategoria(String nombre, String icono) =>
      _api.post('/categorias', {'nombre': nombre, 'icono': icono});

  Future<void> eliminarCategoria(int id) => _api.delete('/categorias/$id');
}
