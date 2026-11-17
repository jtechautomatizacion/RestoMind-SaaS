import '../../core/api/api_client.dart';
import '../../impresion/comprobante.dart';
import 'modelos.dart';

/// Las llamadas de la sala, tipadas. Todas pasan por el ApiClient único.
class MesasRepo {
  MesasRepo(this._api);

  final ApiClient _api;

  static List<T> _lista<T>(Object? v, T Function(Map<String, dynamic>) leer) =>
      [
        for (final e in v as List<dynamic>? ?? const [])
          leer(e as Map<String, dynamic>),
      ];

  Future<List<Mesa>> mesas() async =>
      _lista(await _api.get('/mesas'), Mesa.desdeJson);

  Future<List<Plato>> carta() async =>
      _lista(await _api.get('/platos'), Plato.desdeJson);

  /// Lo que hoy está en cocina, incluidos los pedidos para llevar (nacen
  /// cobrados, así que solo el monitor los muestra pendientes).
  Future<List<ComandaCocina>> enCocina() async =>
      _lista(await _api.get('/monitor/cocina'), ComandaCocina.desdeJson);

  /// Comandas servidas que esperan la cuenta.
  Future<List<Comanda>> entregadas() async => _lista(
    await _api.get('/comandas', query: {'estado': 'entregado'}),
    Comanda.desdeJson,
  );

  /// Lo que la mesa todavía debe (en cocina o servido).
  Future<List<Comanda>> cuentaDeMesa(int numeroMesa) async => _lista(
    await _api.get('/comandas', query: {'numero_mesa': numeroMesa}),
    Comanda.desdeJson,
  ).where((c) => c.activa).toList();

  /// Total vendido del turno abierto (admin). 0 si no hay turno.
  Future<double> vendidoDelTurno() async {
    final j = await _api.get('/caja/estado') as Map<String, dynamic>;
    return (j['ventas_hasta_ahora'] as num? ?? 0).toDouble();
  }

  Future<Comanda> crearComanda({
    required int numeroMesa,
    required bool paraLlevar,
    required Map<int, int> cantidades,
    required MetodoPago metodo,
  }) async {
    final j = await _api.post('/comandas', {
      'numero_mesa': paraLlevar ? 0 : numeroMesa,
      'tipo_pedido': paraLlevar ? 'llevar' : 'mesa',
      'platos': [
        for (final e in cantidades.entries)
          {'plato_id': e.key, 'cantidad': e.value},
      ],
      // Solo para llevar: el backend rechaza (422) un pedido de mesa que
      // declare método de pago, porque ahí todavía no se cobró nada.
      if (paraLlevar) 'metodo_pago': metodo.api,
    });
    return Comanda.desdeJson(j as Map<String, dynamic>);
  }

  Future<Cobro> cobrar(int mesaId, MetodoPago metodo) async {
    final j = await _api.post('/mesas/$mesaId/cobrar', {
      'metodo_pago': metodo.api,
    });
    return Cobro.desdeJson(j as Map<String, dynamic>);
  }

  /// El tipo de comprobante (boleta o factura) lo decide el servidor según
  /// el documento y el régimen del restaurante.
  Future<Factura> generarComprobante({
    required List<int> comandaIds,
    required String documento,
    required String nombre,
  }) async {
    final j = await _api.post('/facturas/generar', {
      'comanda_ids': comandaIds,
      'documento_comprador': documento.isEmpty ? null : documento,
      // Es la salida para un RUC recién inscrito que el padrón local
      // todavía no tiene.
      'razon_social_manual': nombre.isEmpty ? null : nombre,
    });
    return Factura.desdeJson(j as Map<String, dynamic>);
  }

  Future<ConsultaDocumento> consultarDocumento(String numero) async =>
      ConsultaDocumento.desdeJson(
        await _api.get('/documento/$numero') as Map<String, dynamic>,
      );

  /// Recuerda el nombre de un DNI para la próxima visita de esa persona.
  Future<void> recordarDocumento(String dni, String nombre) =>
      _api.post('/documento/$dni', {'nombre': nombre});

  Future<void> marcarEntregada(int comandaId) =>
      _api.patch('/comandas/$comandaId/estado', {'estado': 'entregado'});

  Future<void> guardarMesa({
    int? id,
    required int numero,
    required int capacidad,
    String? ubicacion,
  }) {
    final datos = {
      'numero': numero,
      'capacidad': capacidad,
      'ubicacion': ubicacion,
    };
    return id == null
        ? _api.post('/mesas', datos)
        : _api.patch('/mesas/$id', datos);
  }

  Future<void> eliminarMesa(int id) => _api.delete('/mesas/$id');
}
