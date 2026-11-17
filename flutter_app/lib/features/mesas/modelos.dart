/// Modelos de la sala: mesas, carta, pedidos, cobro y comprobante. Se leen de
/// los esquemas de backend/schemas.py (MesaResponse, PlatoResponse,
/// ComandaResponse, MonitorComandaItem, CobroResponse). El comprobante vive en
/// lib/impresion/comprobante.dart: lo comparten la sala y Admin > Boletas.
library;

import '../../core/formato.dart';

int _entero(Object? v) => (v as num?)?.toInt() ?? 0;

List<Map<String, dynamic>> _mapas(Object? v) => [
  for (final e in v as List<dynamic>? ?? const []) e as Map<String, dynamic>,
];

/// Cómo se ve una mesa. Tres estados y no dos: una mesa ocupada puede estar
/// esperando la comida o esperando que le cobren, y para quien atiende son
/// situaciones muy distintas (en la segunda hay plata sobre la mesa).
enum EstadoMesa { libre, cocinando, porCobrar }

class Mesa {
  const Mesa({
    required this.id,
    required this.numero,
    required this.capacidad,
    required this.ocupada,
    required this.cuentaActual,
    this.ubicacion,
  });

  factory Mesa.desdeJson(Map<String, dynamic> j) => Mesa(
    id: _entero(j['id']),
    numero: _entero(j['numero']),
    capacidad: _entero(j['capacidad']),
    ocupada: j['estado'] == 'ocupada',
    cuentaActual: aDouble(j['cuenta_actual']),
    ubicacion: j['ubicacion'] as String?,
  );

  final int id;
  final int numero;
  final int capacidad;
  final bool ocupada;
  final double cuentaActual;
  final String? ubicacion;
}

class Plato {
  const Plato({
    required this.id,
    required this.nombre,
    required this.categoria,
    required this.precio,
    required this.activo,
    this.descripcion,
    this.imagenUrl,
  });

  factory Plato.desdeJson(Map<String, dynamic> j) => Plato(
    id: _entero(j['id']),
    nombre: j['nombre'] as String? ?? '',
    categoria: j['categoria'] as String? ?? '',
    precio: aDouble(j['precio_venta']),
    activo: j['estado'] == 'activo',
    descripcion: j['descripcion'] as String?,
    imagenUrl: j['imagen_url'] as String?,
  );

  final int id;
  final String nombre;
  final String categoria;
  final double precio;
  final bool activo;
  final String? descripcion;
  final String? imagenUrl;
}

class LineaComanda {
  const LineaComanda({
    required this.nombre,
    required this.cantidad,
    required this.precioUnitario,
    required this.subtotal,
  });

  factory LineaComanda.desdeJson(Map<String, dynamic> j) => LineaComanda(
    nombre: j['nombre'] as String? ?? '',
    cantidad: _entero(j['cantidad']),
    precioUnitario: aDouble(j['precio_unitario']),
    subtotal: aDouble(j['subtotal']),
  );

  final String nombre;
  final int cantidad;
  final double precioUnitario;
  final double subtotal;
}

class Comanda {
  const Comanda({
    required this.id,
    required this.numeroMesa,
    required this.paraLlevar,
    required this.estado,
    required this.total,
    required this.lineas,
    this.creadoEn,
  });

  factory Comanda.desdeJson(Map<String, dynamic> j) => Comanda(
    id: _entero(j['id']),
    numeroMesa: _entero(j['numero_mesa']),
    paraLlevar: j['tipo_pedido'] == 'llevar',
    estado: j['estado'] as String? ?? '',
    total: aDouble(j['total_cuenta']),
    lineas: [for (final l in _mapas(j['platos'])) LineaComanda.desdeJson(l)],
    creadoEn: fechaLocal(j['creado_en']),
  );

  final int id;
  final int numeroMesa;
  final bool paraLlevar;
  final String estado;
  final double total;
  final List<LineaComanda> lineas;
  final DateTime? creadoEn;

  bool get enCocina => estado == 'cocina';

  /// Activa = la mesa todavía la debe (en cocina o ya servida).
  bool get activa => estado == 'cocina' || estado == 'entregado';
}

/// Un pedido en la pantalla de cocina (GET /monitor/cocina).
class ComandaCocina {
  const ComandaCocina({
    required this.id,
    required this.numeroMesa,
    required this.minutos,
    required this.platos,
    this.creadoEn,
  });

  factory ComandaCocina.desdeJson(Map<String, dynamic> j) => ComandaCocina(
    id: _entero(j['id']),
    numeroMesa: _entero(j['numero_mesa']),
    minutos: _entero(j['minutos_transcurridos']),
    platos: [
      for (final p in _mapas(j['platos']))
        (
          cantidad: _entero(p['cantidad']),
          nombre: p['nombre'] as String? ?? '',
        ),
    ],
    creadoEn: fechaLocal(j['creado_en']),
  );

  final int id;
  final int numeroMesa;
  final int minutos;
  final List<({int cantidad, String nombre})> platos;
  final DateTime? creadoEn;
}

/// "Mesa 5" o "Para llevar #12": numero_mesa vale 0 en un pedido para llevar,
/// y "Mesa 0" mandaría a buscar una mesa que no existe.
String rotuloPedido(int numeroMesa, int id) =>
    numeroMesa > 0 ? 'Mesa $numeroMesa' : 'Para llevar #$id';

/// Dos bolsillos a propósito: efectivo es lo que tiene que estar en el cajón
/// al arquear; Yape y Plin terminan en el mismo celular.
enum MetodoPago {
  efectivo('efectivo', 'Efectivo'),
  yape('yape', 'Yape/Plin');

  const MetodoPago(this.api, this.etiqueta);
  final String api;
  final String etiqueta;

  static MetodoPago desdeApi(Object? v) =>
      values.firstWhere((m) => m.api == v, orElse: () => efectivo);
}

class Cobro {
  const Cobro({
    required this.mesaNumero,
    required this.total,
    required this.comandaIds,
    required this.metodo,
  });

  factory Cobro.desdeJson(Map<String, dynamic> j) => Cobro(
    mesaNumero: _entero(j['mesa_numero']),
    total: aDouble(j['total_cobrado']),
    comandaIds: [
      for (final i in j['comanda_ids'] as List<dynamic>? ?? const [])
        _entero(i),
    ],
    metodo: MetodoPago.desdeApi(j['metodo_pago']),
  );

  final int mesaNumero;
  final double total;
  final List<int> comandaIds;
  final MetodoPago metodo;
}

/// Resultado de GET /documento/{numero}. "No encontrado" no es un error: el
/// cajero escribe el nombre a mano y sigue cobrando.
class ConsultaDocumento {
  const ConsultaDocumento({
    required this.encontrado,
    this.nombre,
    this.advertencia,
  });

  factory ConsultaDocumento.desdeJson(Map<String, dynamic> j) =>
      ConsultaDocumento(
        encontrado: j['encontrado'] == true,
        nombre: j['nombre'] as String?,
        advertencia: j['advertencia'] as String?,
      );

  final bool encontrado;
  final String? nombre;
  final String? advertencia;
}
