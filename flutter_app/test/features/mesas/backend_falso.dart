import 'dart:convert';

import 'package:http/http.dart' as http;

/// Un backend de sala en memoria para las pruebas de Mesas y "Atiendo solo".
/// Cada prueba arma solo lo que le importa; lo demás responde vacío.
class BackendSala {
  List<Map<String, dynamic>> mesas = [];
  List<Map<String, dynamic>> cocina = [];
  List<Map<String, dynamic>> comandas = [];
  List<Map<String, dynamic>> platos = [
    plato(101, 'Ceviche', 'Cebiches', 45),
    plato(102, 'Lomo saltado', 'Fondos', 38),
  ];
  (int, Object?) factura = (201, facturaJson());
  (int, Object?) documento = (
    200,
    {'documento': '', 'tipo': 'DNI', 'encontrado': false},
  );
  Map<String, dynamic> identidad = {};

  (int, Object?) call(http.Request r) {
    final ruta = r.url.path.replaceFirst('/api', '');
    final q = r.url.queryParameters;
    switch ((r.method, ruta)) {
      case ('GET', '/mesas'):
        return (200, mesas);
      case ('GET', '/monitor/cocina'):
        return (200, cocina);
      case ('GET', '/platos'):
        return (200, platos);
      case ('GET', '/comandas'):
        return (
          200,
          comandas
              .where(
                (c) =>
                    (q['estado'] == null || c['estado'] == q['estado']) &&
                    (q['numero_mesa'] == null ||
                        '${c['numero_mesa']}' == q['numero_mesa']),
              )
              .toList(),
        );
      case ('POST', '/comandas'):
        final b = jsonDecode(r.body) as Map<String, dynamic>;
        return (
          201,
          comanda(
            900,
            b['numero_mesa'] as int,
            b['tipo_pedido'] == 'llevar' ? 'cobrado' : 'cocina',
            45,
            llevar: b['tipo_pedido'] == 'llevar',
          ),
        );
      case ('POST', '/mesas'):
        return (201, mesa(50, 9));
      case ('GET', '/caja/estado'):
        return (200, {'hay_caja_abierta': true, 'ventas_hasta_ahora': 321.5});
      case ('POST', '/facturas/generar'):
        return factura;
      case ('GET', '/auth/me'):
        return (200, identidad);
    }
    final cobro = RegExp(r'^/mesas/(\d+)/cobrar$').firstMatch(ruta);
    if (r.method == 'POST' && cobro != null) {
      final id = int.parse(cobro.group(1)!);
      final numero = mesas.firstWhere((m) => m['id'] == id)['numero'];
      final activas = comandas
          .where(
            (c) => c['numero_mesa'] == numero && c['estado'] == 'entregado',
          )
          .toList();
      return (
        200,
        {
          'mesa_numero': numero,
          'total_cobrado': activas.fold<num>(
            0,
            (s, c) => s + (c['total_cuenta'] as num),
          ),
          'comandas_cerradas': activas.length,
          'comanda_ids': [for (final c in activas) c['id']],
          'metodo_pago':
              (jsonDecode(r.body) as Map<String, dynamic>)['metodo_pago'],
        },
      );
    }
    if (r.method == 'GET' && ruta.startsWith('/documento/')) return documento;
    if (r.method == 'POST' && ruta.startsWith('/documento/')) return (200, {});
    if (r.method == 'PATCH' && ruta.startsWith('/comandas/')) return (200, {});
    return (404, {'detail': 'No existe en el backend falso: $ruta'});
  }
}

Map<String, dynamic> mesa(
  int id,
  int numero, {
  bool ocupada = false,
  double cuenta = 0,
}) => {
  'id': id,
  'cliente_id': 'test-cliente-001',
  'numero': numero,
  'capacidad': 4,
  'ubicacion': null,
  'estado': ocupada ? 'ocupada' : 'disponible',
  'creado_en': '2026-11-17T12:00:00',
  'cuenta_actual': cuenta,
};

Map<String, dynamic> plato(int id, String nombre, String cat, double precio) =>
    {
      'id': id,
      'cliente_id': 'test-cliente-001',
      'nombre': nombre,
      'categoria': cat,
      'precio_venta': precio,
      'descripcion': null,
      'imagen_url': null,
      'estado': 'activo',
      'creado_en': '2026-11-01T12:00:00',
    };

Map<String, dynamic> comanda(
  int id,
  int numeroMesa,
  String estado,
  double total, {
  bool llevar = false,
}) => {
  'id': id,
  'cliente_id': 'test-cliente-001',
  'numero_mesa': numeroMesa,
  'tipo_pedido': llevar ? 'llevar' : 'mesa',
  'estado': estado,
  'metodo_pago': null,
  'total_cuenta': total,
  'platos': [
    {
      'plato_id': 101,
      'nombre': 'Ceviche',
      'cantidad': 1,
      'precio_unitario': total,
      'subtotal': total,
    },
  ],
  'creado_en': '2026-11-17T12:00:00',
};

Map<String, dynamic> enCocina(int id, int numeroMesa) => {
  'id': id,
  'numero_mesa': numeroMesa,
  'estado': 'cocina',
  'creado_en': '2026-11-17T12:00:00',
  'minutos_transcurridos': 4,
  'platos': [
    {'nombre': 'Ceviche', 'cantidad': 2},
  ],
};

Map<String, dynamic> facturaJson({String estado = 'aceptada'}) => {
  'id': 1,
  'numero_mesa': 3,
  'serie': 'B001',
  'numero_correlativo': 7,
  'numero_boleta': 'B001-00000007',
  'subtotal': 80.51,
  'igv': 14.49,
  'total': 95.0,
  'estado': estado,
  'creado_en': '2026-11-17T12:00:00',
  'fecha_emision_local': '2026-11-17',
  'hora_emision_local': '07:00:00',
  'ruc_emisor': '20000000001',
  'razon_social_emisor': 'Restaurante de Prueba SAC',
  'nombre_emisor': 'Restaurante de Prueba',
  'tipo_documento_comprador': '1',
  'numero_documento_comprador': '73081441',
  'nombre_comprador': '-',
  'detalles': [
    {
      'descripcion': 'Ceviche',
      'cantidad': 1,
      'precio_unitario': 95.0,
      'subtotal': 95.0,
    },
  ],
};
