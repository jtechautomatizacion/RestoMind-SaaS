import '../../core/formato.dart';

/// A partir de estos minutos un pedido se pinta en rojo: el cliente ya lleva
/// un cuarto de hora esperando (CU-03).
const alertaMinutos = 15;

class PlatoCocina {
  const PlatoCocina({required this.nombre, required this.cantidad});

  factory PlatoCocina.desdeJson(Map<String, dynamic> j) => PlatoCocina(
    nombre: j['nombre'] as String? ?? '',
    cantidad: (j['cantidad'] as num?)?.toInt() ?? 0,
  );

  final String nombre;
  final int cantidad;
}

/// Un pedido en la cola de cocina (`GET /monitor/cocina`).
class ComandaCocina {
  const ComandaCocina({
    required this.id,
    required this.numeroMesa,
    required this.creadoEn,
    required this.minutos,
    required this.platos,
  });

  factory ComandaCocina.desdeJson(Map<String, dynamic> j) => ComandaCocina(
    id: (j['id'] as num).toInt(),
    numeroMesa: (j['numero_mesa'] as num?)?.toInt() ?? 0,
    creadoEn: fechaLocal(j['creado_en']),
    // Lo calcula el servidor con SU reloj: el de un tablet de cocina puede
    // estar atrasado y marcar como recién llegado un pedido de hace 20 min.
    minutos: (j['minutos_transcurridos'] as num?)?.toInt() ?? 0,
    platos: [
      for (final p in j['platos'] as List<dynamic>? ?? const [])
        PlatoCocina.desdeJson(p as Map<String, dynamic>),
    ],
  );

  final int id;

  /// 0 en los pedidos para llevar: no tienen mesa.
  final int numeroMesa;
  final DateTime? creadoEn;
  final int minutos;
  final List<PlatoCocina> platos;

  bool get paraLlevar => numeroMesa <= 0;
  bool get atrasada => minutos >= alertaMinutos;

  /// "Mesa 5" o "Para llevar #412" (mismo rótulo que rotuloComanda en app.js).
  String get rotulo => paraLlevar ? 'Para llevar #$id' : 'Mesa $numeroMesa';
}

/// El más antiguo primero: es el que más tiempo lleva esperando.
List<ComandaCocina> ordenarPorAntiguedad(Iterable<ComandaCocina> comandas) {
  final lista = [...comandas];
  lista.sort((a, b) {
    final fa = a.creadoEn, fb = b.creadoEn;
    if (fa == null || fb == null) return b.minutos.compareTo(a.minutos);
    return fa.compareTo(fb);
  });
  return lista;
}
