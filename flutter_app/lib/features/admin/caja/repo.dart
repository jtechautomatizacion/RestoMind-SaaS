import '../../../core/api/api_client.dart';
import 'modelos.dart';

/// Validador de caja. Todo admin-only salvo /caja/gate, que vive en el shell.
class CajaRepo {
  const CajaRepo(this._api);

  final ApiClient _api;

  Future<EstadoCaja> estado() async => EstadoCaja.desdeJson(
    await _api.get('/caja/estado') as Map<String, dynamic>,
  );

  /// Últimos cierres (no incluye el turno abierto).
  Future<List<Turno>> historial() async {
    final lista =
        await _api.get('/caja/historial', query: {'limit': 30})
            as List<dynamic>;
    return [for (final j in lista) Turno.desdeJson(j as Map<String, dynamic>)];
  }

  Future<Turno> abrir({
    required double saldoInicial,
    String? nombreTurno,
  }) async => Turno.desdeJson(
    await _api.post('/caja/abrir', {
          'saldo_inicial': saldoInicial,
          'nombre_turno': nombreTurno,
        })
        as Map<String, dynamic>,
  );

  Future<Turno> cerrar({
    required double saldoContado,
    required double retiros,
    String? razon,
  }) async => Turno.desdeJson(
    await _api.post('/caja/cerrar', {
          'saldo_contado': saldoContado,
          'retiros_personales': retiros,
          'razon_discrepancia': razon,
        })
        as Map<String, dynamic>,
  );
}
