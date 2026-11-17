import '../../core/api/api_client.dart';
import 'modelos.dart';

class CocinaRepo {
  const CocinaRepo(this._api);

  final ApiClient _api;

  Future<List<ComandaCocina>> pendientes() async {
    final lista = await _api.get('/monitor/cocina') as List<dynamic>? ?? [];
    return ordenarPorAntiguedad(
      lista.map((j) => ComandaCocina.desdeJson(j as Map<String, dynamic>)),
    );
  }

  /// "Listo": de mesa pasa a 'entregado'; para llevar, el backend anota
  /// `entregado_en` con este mismo pedido.
  Future<void> marcarEntregada(int id) =>
      _api.patch('/comandas/$id/estado', {'estado': 'entregado'});

  /// Encola el ticket de cocina otra vez: sale por la impresora de la
  /// estación cocina, que puede no ser la de este aparato.
  Future<void> reimprimir(int id) => _api.post('/impresion/reimprimir', {
    'comanda_id': id,
    'tipo_documento': 'cocina',
  });
}
