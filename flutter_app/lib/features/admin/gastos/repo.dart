import '../../../core/api/api_client.dart';
import '../../../core/formato.dart';
import 'modelos.dart';

/// Lo que se carga de una vez para pintar Gastos e inventario.
class DatosGastos {
  const DatosGastos(this.compras, this.insumos);
  final List<Compra> compras;
  final List<Insumo> insumos;
}

/// Llamadas de Admin > Gastos (backend/routes/compras.py, insumos.py y
/// movimientos.py).
class GastosRepo {
  const GastosRepo(this._api);
  final ApiClient _api;

  Future<DatosGastos> cargar() async {
    final (compras, insumos) = await (
      _api.get('/compras'),
      _api.get('/insumos'),
    ).wait;
    return DatosGastos(
      [
        for (final c in compras as List<dynamic>)
          Compra.desdeJson(c as Map<String, dynamic>),
      ],
      [
        for (final i in insumos as List<dynamic>)
          Insumo.desdeJson(i as Map<String, dynamic>),
      ],
    );
  }

  // ------------------------------------------------------------ gastos ---

  Future<void> crearCompra(BorradorCompra b) =>
      _api.post('/compras', b.aJsonNuevo());

  Future<void> editarCompra(int id, BorradorCompra b) =>
      _api.patch('/compras/$id', b.aJsonEdicion());

  Future<void> eliminarCompra(int id) => _api.delete('/compras/$id');

  /// Anula o restaura: un gasto de otro día no se borra, se anula, para no
  /// perder historial financiero.
  Future<void> cambiarEstadoCompra(int id, {required bool anular}) =>
      _api.patch('/compras/$id/estado', {
        'estado': anular ? 'cancelado' : 'registrado',
      });

  // --------------------------------------------------------- insumos ---

  Future<void> crearInsumo(BorradorInsumo b) =>
      _api.post('/insumos', b.aJson());

  Future<void> editarInsumo(int id, BorradorInsumo b) =>
      _api.patch('/insumos/$id', b.aJson());

  Future<void> eliminarInsumo(int id) => _api.delete('/insumos/$id');

  // ----------------------------------------------------- movimientos ---

  Future<Movimiento> registrarMovimiento(
    int insumoId, {
    required TipoMovimiento tipo,
    required double cantidad,
    required String razon,
    required DateTime fecha,
  }) async => Movimiento.desdeJson(
    await _api.post('/insumos/$insumoId/movimientos', {
          'tipo': tipo.name,
          'cantidad': cantidad,
          'razon': razon,
          'fecha': fechaIso(fecha),
        })
        as Map<String, dynamic>,
  );

  Future<List<Movimiento>> historial(int insumoId) async {
    final lista = await _api.get(
      '/insumos/$insumoId/movimientos',
      query: const {'limite': 50},
    );
    return [
      for (final m in lista as List<dynamic>)
        Movimiento.desdeJson(m as Map<String, dynamic>),
    ];
  }

  /// No borra: el backend deja el original y agrega uno inverso que lo
  /// corrige. Devuelve ese inverso (trae el stock ya corregido).
  Future<Movimiento> revertir(int insumoId, int movimientoId) async =>
      Movimiento.desdeJson(
        await _api.delete('/insumos/$insumoId/movimientos/$movimientoId')
            as Map<String, dynamic>,
      );
}
