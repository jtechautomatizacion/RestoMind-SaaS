import 'package:flutter/foundation.dart';

import '../../../core/formato.dart';
import '../../../design/widgets.dart';

// ------------------------------------------------------------- gastos ----

/// Un gasto de caja chica (CompraResponse). [fecha] es de calendario
/// (`2026-11-17`), elegida por el admin: no es UTC y no se convierte.
@immutable
class Compra {
  const Compra({
    required this.id,
    required this.descripcion,
    required this.monto,
    required this.fecha,
    required this.estado,
    this.categoria,
  });

  factory Compra.desdeJson(Map<String, dynamic> j) => Compra(
    id: j['id'] as int,
    descripcion: j['descripcion'] as String? ?? '',
    categoria: j['categoria'] as String?,
    monto: aDouble(j['monto']),
    fecha: j['fecha'] as String? ?? '',
    estado: j['estado'] as String? ?? 'registrado',
  );

  final int id;
  final String descripcion;
  final String? categoria;
  final double monto;
  final String fecha;
  final String estado;

  bool get registrado => estado == 'registrado';
}

/// Lo que se manda al registrar o editar un gasto. Al editar NO va el monto:
/// el backend no lo deja cambiar (rompería el cuadre de caja de ese día).
@immutable
class BorradorCompra {
  const BorradorCompra({
    required this.descripcion,
    required this.monto,
    required this.fecha,
    this.categoria,
  });

  final String descripcion;
  final String? categoria;
  final double monto;
  final DateTime fecha;

  Map<String, Object?> aJsonNuevo() => {...aJsonEdicion(), 'monto': monto};

  Map<String, Object?> aJsonEdicion() => {
    'descripcion': descripcion,
    'categoria': categoria,
    'fecha': fechaIso(fecha),
  };
}

const categoriasGasto = ['Insumos', 'Servicios', 'Otros'];

/// Un gasto de mañana descuadraría la caja de hoy: el backend lo rechaza, y
/// el formulario lo dice antes de mandarlo.
String? errorFechaGasto(DateTime fecha, {DateTime? hoy}) {
  final h = hoy ?? DateTime.now();
  final dia = DateTime(fecha.year, fecha.month, fecha.day);
  return dia.isAfter(DateTime(h.year, h.month, h.day))
      ? 'La fecha no puede ser futura'
      : null;
}

/// Gastos de un mismo día, con el total de los que siguen vigentes.
@immutable
class DiaDeGastos {
  const DiaDeGastos(this.fecha, this.compras);
  final String fecha;
  final List<Compra> compras;

  double get total =>
      compras.where((c) => c.registrado).fold(0, (suma, c) => suma + c.monto);
}

/// Agrupados por fecha, el día más reciente primero.
List<DiaDeGastos> agruparPorDia(List<Compra> compras) {
  final porFecha = <String, List<Compra>>{};
  for (final c in compras) {
    (porFecha[c.fecha] ??= []).add(c);
  }
  final fechas = porFecha.keys.toList()..sort((a, b) => b.compareTo(a));
  return [for (final f in fechas) DiaDeGastos(f, porFecha[f]!)];
}

/// `2026-11-17` → `17/11/2026`.
String fechaDeCalendario(String iso) {
  final f = DateTime.tryParse(iso);
  return f == null ? iso : fecha(f);
}

// --------------------------------------------------------- inventario ----

enum EstadoInsumo {
  ok('OK', TipoEstado.exito),
  bajo('Bajo', TipoEstado.aviso),
  critico('Crítico', TipoEstado.peligro);

  const EstadoInsumo(this.etiqueta, this.tipo);
  final String etiqueta;
  final TipoEstado tipo;

  static EstadoInsumo de(Object? v) => switch (v) {
    'critico' => critico,
    'bajo' => bajo,
    _ => ok,
  };
}

/// Un insumo del almacén (InsumoResponse). El estado lo calcula el backend
/// comparando el stock contra el mínimo.
@immutable
class Insumo {
  const Insumo({
    required this.id,
    required this.nombre,
    required this.unidad,
    required this.cantidadActual,
    required this.cantidadMinima,
    required this.estado,
  });

  factory Insumo.desdeJson(Map<String, dynamic> j) => Insumo(
    id: j['id'] as int,
    nombre: j['nombre'] as String? ?? '',
    unidad: j['unidad'] as String? ?? '',
    cantidadActual: aDouble(j['cantidad_actual']),
    cantidadMinima: aDouble(j['cantidad_minima']),
    estado: EstadoInsumo.de(j['estado']),
  );

  final int id;
  final String nombre;
  final String unidad;
  final double cantidadActual;
  final double cantidadMinima;
  final EstadoInsumo estado;

  String get stock => '${cantidad(cantidadActual)} $unidad';
}

/// Lo que se manda al crear o editar un insumo.
@immutable
class BorradorInsumo {
  const BorradorInsumo({
    required this.nombre,
    required this.unidad,
    required this.cantidadActual,
    required this.cantidadMinima,
  });

  final String nombre;
  final String unidad;
  final double cantidadActual;
  final double cantidadMinima;

  Map<String, Object?> aJson() => {
    'nombre': nombre,
    'unidad': unidad,
    'cantidad_actual': cantidadActual,
    'cantidad_minima': cantidadMinima,
  };
}

/// Lista cerrada del backend (UNIDADES_VALIDAS): con texto libre, "kg", "Kg"
/// y "kilos" terminarían siendo tres unidades distintas.
const unidades = [
  ('kg', 'Kilos (kg)'),
  ('gramo', 'Gramos'),
  ('litro', 'Litros'),
  ('ml', 'Mililitros (ml)'),
  ('unidad', 'Unidades'),
  ('docena', 'Docenas'),
  ('paquete', 'Paquetes'),
  ('caja', 'Cajas'),
];

/// Un stock rara vez es decimal exacto: 20 se muestra "20", no "20.00", pero
/// medio kilo de ají sigue viéndose "0.5".
String cantidad(num n) {
  if (n == n.roundToDouble()) return n.toStringAsFixed(0);
  return n
      .toStringAsFixed(2)
      .replaceFirst(RegExp(r'0+$'), '')
      .replaceFirst(RegExp(r'\.$'), '');
}

/// Cantidad tipeada: coma o punto, hasta dos decimales.
double? leerCantidad(String texto) {
  final t = texto.trim().replaceAll(',', '.');
  if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(t)) return null;
  return double.parse(t);
}

/// Resumen que se ve con el inventario cerrado: tiene que alcanzar para
/// decidir si vale la pena abrirlo. null si no hay insumos.
(String, TipoEstado)? resumenInventario(List<Insumo> insumos) {
  if (insumos.isEmpty) return null;
  final criticos = insumos.where((i) => i.estado == EstadoInsumo.critico);
  final bajos = insumos.where((i) => i.estado == EstadoInsumo.bajo);
  if (criticos.isNotEmpty) {
    final n = criticos.length;
    return ('$n crítico${n == 1 ? '' : 's'}', TipoEstado.peligro);
  }
  if (bajos.isNotEmpty) {
    final n = bajos.length;
    return ('$n bajo${n == 1 ? '' : 's'}', TipoEstado.aviso);
  }
  return ('Todo OK', TipoEstado.exito);
}

/// Insumos por debajo del mínimo, los críticos primero: es lo que puede
/// faltar hoy mismo.
List<Insumo> enAlerta(List<Insumo> insumos) =>
    insumos.where((i) => i.estado != EstadoInsumo.ok).toList()
      ..sort((a, b) => b.estado.index.compareTo(a.estado.index));

// --------------------------------------------------------- movimientos ----

enum TipoMovimiento {
  entrada,
  salida;

  String get signo => this == entrada ? '+' : '−';
}

/// Motivos que se ofrecen al registrar ("reversion" lo pone solo el sistema).
const razonesMovimiento = [
  ('compra', 'Llegó mercadería'),
  ('uso', 'Se usó en cocina'),
  ('merma', 'Se echó a perder'),
  ('ajuste', 'Ajuste por conteo'),
  ('otro', 'Otro'),
];

const razonReversion = 'reversion';

String etiquetaRazon(String razon) {
  if (razon == razonReversion) return 'Deshecho';
  for (final (valor, etiqueta) in razonesMovimiento) {
    if (valor == razon) return etiqueta;
  }
  return razon;
}

/// Una entrada o salida de stock (MovimientoResponse).
@immutable
class Movimiento {
  const Movimiento({
    required this.id,
    required this.tipo,
    required this.cantidad,
    required this.razon,
    required this.saldoDespues,
    required this.revertido,
    this.fecha,
    this.usuarioNombre,
  });

  factory Movimiento.desdeJson(Map<String, dynamic> j) => Movimiento(
    id: j['id'] as int,
    tipo: j['tipo'] == 'salida'
        ? TipoMovimiento.salida
        : TipoMovimiento.entrada,
    cantidad: aDouble(j['cantidad']),
    razon: j['razon'] as String? ?? 'otro',
    saldoDespues: aDouble(j['saldo_despues']),
    revertido: j['revertido'] as bool? ?? false,
    fecha: _diaDeNegocio(j['fecha']),
    usuarioNombre: j['usuario_nombre'] as String?,
  );

  final int id;
  final TipoMovimiento tipo;
  final double cantidad;
  final String razon;
  final double saldoDespues;
  final bool revertido;
  final DateTime? fecha;
  final String? usuarioNombre;

  /// Un movimiento ya revertido, o una reversión, no se deshace: el backend
  /// responde 400 y ofrecer el botón sería prometer algo que falla.
  bool get puedeDeshacer => !revertido && razon != razonReversion;
}

/// `fecha` de un movimiento es el DÍA de negocio a medianoche, no un instante
/// UTC: convertirlo a hora local lo correría al día anterior en Perú.
DateTime? _diaDeNegocio(Object? v) => v is String && v.length >= 10
    ? DateTime.tryParse(v.substring(0, 10))
    : null;
