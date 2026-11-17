import '../../core/formato.dart';

/// Mismo tope que MAX_DIAS_RANGO en backend/routes/dashboard.py. El servidor
/// es el que manda; repetirlo acá solo evita esperar el viaje para enterarse.
const maxDiasRango = 366;

/// Atajos del selector. El backend acepta `dias` de 1 a 30.
const diasRapidos = [7, 14, 30];

DateTime _soloFecha(DateTime f) => DateTime(f.year, f.month, f.day);

/// Período consultado: "los últimos N días" o un rango a medida.
class Periodo {
  const Periodo.ultimos(int this.dias) : desde = null, hasta = null;
  const Periodo.rango(DateTime this.desde, DateTime this.hasta) : dias = null;

  final int? dias;
  final DateTime? desde;
  final DateTime? hasta;

  bool get esRango => dias == null;

  @override
  bool operator ==(Object other) =>
      other is Periodo &&
      other.dias == dias &&
      other.desde == desde &&
      other.hasta == hasta;

  @override
  int get hashCode => Object.hash(dias, desde, hasta);

  Map<String, Object?> get query => esRango
      ? {'desde': fechaIso(desde!), 'hasta': fechaIso(hasta!)}
      : {'dias': dias};

  String get etiqueta =>
      esRango ? '${fecha(desde)} - ${fecha(hasta)}' : 'Últimos $dias días';

  /// Las fechas que muestra el selector. "Últimos 7 días" = hoy y los 6
  /// anteriores: 7 fechas exactas, como las cuenta el backend.
  (DateTime, DateTime) fechas(DateTime hoy) {
    if (esRango) return (desde!, hasta!);
    final fin = _soloFecha(hoy);
    return (fin.subtract(Duration(days: dias! - 1)), fin);
  }
}

/// null si el rango sirve; si no, el motivo para mostrar.
String? validarRango(DateTime desde, DateTime hasta) {
  if (desde.isAfter(hasta)) {
    return 'La fecha inicial no puede ser mayor a la final';
  }
  // Por calendario y no con difference(): un cambio de horario de verano
  // haría que un día dure 23 horas y la cuenta quede un día corta.
  final dias =
      DateTime.utc(
        hasta.year,
        hasta.month,
        hasta.day,
      ).difference(DateTime.utc(desde.year, desde.month, desde.day)).inDays +
      1;
  if (dias > maxDiasRango) {
    return 'El rango no puede superar $maxDiasRango días (eligió $dias)';
  }
  return null;
}

class DiaSerie {
  const DiaSerie({
    required this.fecha,
    required this.ventas,
    required this.gastos,
    required this.ganancia,
  });

  factory DiaSerie.desdeJson(Map<String, dynamic> j) => DiaSerie(
    // "2026-11-17" es un día del restaurante, no un instante: se lee como
    // fecha local para no correrlo un día por la zona horaria.
    fecha: DateTime.parse(j['fecha'] as String),
    ventas: aDouble(j['ventas']),
    gastos: aDouble(j['gastos']),
    ganancia: aDouble(j['ganancia']),
  );

  final DateTime fecha;
  final double ventas;
  final double gastos;
  final double ganancia;

  /// Margen sobre lo vendido; null si ese día no hubo ventas.
  double? get margen => margenDe(ventas, ganancia);
}

double? margenDe(double ventas, double ganancia) =>
    ventas > 0 ? ganancia / ventas * 100 : null;

class Totales {
  const Totales({
    required this.ventas,
    required this.gastos,
    required this.ganancia,
  });

  factory Totales.desdeJson(Map<String, dynamic> j) => Totales(
    ventas: aDouble(j['ventas']),
    gastos: aDouble(j['gastos']),
    ganancia: aDouble(j['ganancia']),
  );

  final double ventas;
  final double gastos;
  final double ganancia;

  double? get margen => margenDe(ventas, ganancia);
}

class TopPlato {
  const TopPlato({
    required this.nombre,
    required this.cantidad,
    required this.ingresos,
  });

  factory TopPlato.desdeJson(Map<String, dynamic> j) => TopPlato(
    nombre: j['nombre'] as String? ?? '',
    cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
    ingresos: aDouble(j['ingresos']),
  );

  final String nombre;
  final int cantidad;
  final double ingresos;
}

class TopGasto {
  const TopGasto({
    required this.categoria,
    required this.cantidad,
    required this.monto,
  });

  factory TopGasto.desdeJson(Map<String, dynamic> j) => TopGasto(
    categoria: j['categoria'] as String? ?? '',
    cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
    monto: aDouble(j['monto']),
  );

  final String categoria;
  final int cantidad;
  final double monto;
}

/// Una fila de "Salón y mostrador" o de "Efectivo y Yape".
class VentaPorTipo {
  const VentaPorTipo({
    required this.tipo,
    required this.pedidos,
    required this.total,
  });

  factory VentaPorTipo.desdeJson(Map<String, dynamic> j) => VentaPorTipo(
    tipo: j['tipo'] as String? ?? '',
    pedidos: (j['pedidos'] as num?)?.toInt() ?? 0,
    total: aDouble(j['total']),
  );

  final String tipo;
  final int pedidos;
  final double total;
}

const etiquetasTipoPedido = {'mesa': 'En salón', 'llevar': 'Para llevar'};
const etiquetasMetodoPago = {'efectivo': 'Efectivo', 'yape': 'Yape/Plin'};

/// `GET /dashboard/resumen`.
class Resumen {
  const Resumen({
    required this.serie,
    required this.totales,
    required this.topPlatos,
    required this.topGastos,
    required this.porTipoPedido,
    required this.porMetodoPago,
  });

  factory Resumen.desdeJson(Map<String, dynamic> j) {
    List<T> lista<T>(String clave, T Function(Map<String, dynamic>) leer) => [
      for (final e in j[clave] as List<dynamic>? ?? const [])
        leer(e as Map<String, dynamic>),
    ];
    return Resumen(
      serie: lista('serie', DiaSerie.desdeJson),
      totales: Totales.desdeJson(
        j['totales'] as Map<String, dynamic>? ?? const {},
      ),
      topPlatos: lista('top_platos', TopPlato.desdeJson),
      topGastos: lista('top_gastos', TopGasto.desdeJson),
      porTipoPedido: lista('por_tipo_pedido', VentaPorTipo.desdeJson),
      porMetodoPago: lista('por_metodo_pago', VentaPorTipo.desdeJson),
    );
  }

  /// En orden de fecha ascendente, como lo arma el backend.
  final List<DiaSerie> serie;
  final Totales totales;
  final List<TopPlato> topPlatos;
  final List<TopGasto> topGastos;
  final List<VentaPorTipo> porTipoPedido;
  final List<VentaPorTipo> porMetodoPago;
}
