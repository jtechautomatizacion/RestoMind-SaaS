import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/api/api_error.dart';
import 'modelos.dart';
import 'repo.dart';

/// Mesas que esperan la cuenta (columna 3 de "Atiendo solo").
class PorCobrar {
  PorCobrar(this.numero, this.desde);
  final int numero;
  DateTime? desde;
  double total = 0;
  int pedidos = 0;
}

/// Lo que se ve de la sala, con su propio pulso de fondo.
///
/// Sin este reloj la pantalla se congela: lo que pasa en OTRO aparato (otro
/// mozo ocupa la 7, cocina marca un plato listo, el admin agrega una mesa) no
/// llegaría nunca. Lo usan la grilla clásica y "Atiendo solo"; la página
/// tiene uno solo, así el mismo dato no viaja dos veces por el wifi del local.
class Sala extends ChangeNotifier {
  Sala(
    this.repo, {
    required bool unificada,
    required this.esAdmin,
    required this.conCarta,
  }) : _unificada = unificada;

  static const intervalo = Duration(seconds: 5);

  /// La carta cambia muchísimo menos que las mesas: se pide cada 6 vueltas
  /// (30 s) en vez de en cada una.
  static const vueltasPorCarta = 6;

  final MesasRepo repo;
  final bool esAdmin;

  /// Quien solo cobra no toma pedidos: no necesita la carta.
  final bool conCarta;

  bool _unificada;
  Timer? _reloj;
  int _vueltas = 0;
  bool _cerrada = false;
  Future<void>? _enCurso;
  bool _otraVez = false;

  List<Mesa> mesas = const [];
  List<ComandaCocina> cocina = const [];
  List<Comanda> entregadas = const [];
  List<Plato> carta = const [];

  /// Vendido del turno; null si no aplica (no admin) o no se pudo leer.
  double? vendido;
  bool cargada = false;
  ApiError? error;

  bool get unificada => _unificada;
  set unificada(bool v) {
    if (v == _unificada) return;
    _unificada = v;
    unawaited(refrescar());
  }

  void iniciar() {
    unawaited(refrescar());
    if (conCarta) unawaited(refrescarCarta());
    _reloj ??= Timer.periodic(intervalo, (_) => _vuelta());
  }

  void _vuelta() {
    _vueltas++;
    if (conCarta && _vueltas % vueltasPorCarta == 0) {
      // Un plato nuevo, o uno que el admin desactivó, también tiene que
      // llegarle al mozo sin recargar la app.
      unawaited(refrescarCarta());
    }
    unawaited(refrescar());
  }

  /// Trae todo de nuevo. Si ya hay un pedido en vuelo, se repite al terminar:
  /// el que estaba viajando pudo salir ANTES del cobro que motivó esta
  /// llamada, y pintaría la mesa todavía ocupada.
  Future<void> refrescar() {
    if (_enCurso != null) {
      _otraVez = true;
      return _enCurso!;
    }
    return _enCurso = _traer().whenComplete(() {
      _enCurso = null;
      if (_otraVez && !_cerrada) {
        _otraVez = false;
        unawaited(refrescar());
      }
    });
  }

  Future<void> _traer() async {
    // Se fija al salir: si el interruptor cambia mientras viaja, las
    // respuestas siguen correspondiendo a lo que se pidió.
    final uni = _unificada;
    try {
      final r = await Future.wait<Object?>([
        repo.mesas(),
        repo.enCocina(),
        if (uni) repo.entregadas(),
        if (uni && esAdmin) _vendido(),
      ]);
      mesas = r[0]! as List<Mesa>;
      cocina = r[1]! as List<ComandaCocina>;
      if (uni) entregadas = r[2]! as List<Comanda>;
      vendido = uni && esAdmin ? r[3] as double? : null;
      cargada = true;
      error = null;
    } on ApiError catch (e) {
      // Sin señal se sigue mostrando lo último conocido: una pantalla un poco
      // vieja sirve más que una en blanco en plena atención.
      if (!cargada) error = e;
    }
    if (!_cerrada) notifyListeners();
  }

  Future<double?> _vendido() async {
    try {
      return await repo.vendidoDelTurno();
    } on ApiError {
      return null;
    }
  }

  Future<void> refrescarCarta() async {
    try {
      carta = await repo.carta();
    } on ApiError {
      // Se sigue con la carta que ya se tenía.
    }
  }

  // ------------------------------------------------------- derivados -----

  Set<int> get mesasEnCocina => {for (final c in cocina) c.numeroMesa};

  EstadoMesa estadoDe(Mesa m) {
    if (!m.ocupada) return EstadoMesa.libre;
    return mesasEnCocina.contains(m.numero)
        ? EstadoMesa.cocinando
        : EstadoMesa.porCobrar;
  }

  /// Mesas con pedidos servidos y NINGUNO todavía en cocina. El filtro no es
  /// cosmético: POST /mesas/{id}/cobrar rechaza si queda algo en cocina, y
  /// una mesa que pidió postre aparecería acá con un Cobrar que falla siempre.
  /// La que espera hace más rato va primero.
  List<PorCobrar> get porCobrar {
    final enCocina = mesasEnCocina;
    final porMesa = <int, PorCobrar>{};
    for (final c in entregadas) {
      if (enCocina.contains(c.numeroMesa)) continue;
      final g = porMesa.putIfAbsent(
        c.numeroMesa,
        () => PorCobrar(c.numeroMesa, c.creadoEn),
      );
      g.total += c.total;
      g.pedidos++;
      final desde = g.desde;
      if (c.creadoEn != null &&
          (desde == null || c.creadoEn!.isBefore(desde))) {
        g.desde = c.creadoEn;
      }
    }
    final lista = porMesa.values.toList()
      ..sort(
        (a, b) => (a.desde ?? DateTime(0)).compareTo(b.desde ?? DateTime(0)),
      );
    return lista;
  }

  /// Hace cuántos minutos espera cada mesa ocupada, con lo que ya está en
  /// memoria: este dato no justifica una consulta más cada 5 segundos.
  Map<int, int> minutosPorMesa(DateTime ahora) {
    final desde = <int, DateTime>{};
    void anotar(int mesa, DateTime? t) {
      if (t == null) return;
      final previo = desde[mesa];
      if (previo == null || t.isBefore(previo)) desde[mesa] = t;
    }

    for (final c in cocina) {
      anotar(c.numeroMesa, c.creadoEn);
    }
    for (final c in entregadas) {
      anotar(c.numeroMesa, c.creadoEn);
    }
    return {
      for (final e in desde.entries)
        e.key: ahora.difference(e.value).inMinutes.clamp(0, 1 << 20),
    };
  }

  @override
  void dispose() {
    _cerrada = true;
    _reloj?.cancel();
    super.dispose();
  }
}
