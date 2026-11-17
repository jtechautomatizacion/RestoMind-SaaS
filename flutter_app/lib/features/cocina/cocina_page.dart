import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/formato.dart';

import '../../core/api/api_error.dart';
import '../../core/servicios.dart';
import '../../design/papel.dart';
import '../../design/widgets.dart';
import 'modelos.dart';
import 'repo.dart';

/// CU-03: monitor de cocina. Se actualiza solo cada pocos segundos, sin que
/// el cocinero toque nada, y el pedido más antiguo va primero.
class CocinaPage extends StatefulWidget {
  const CocinaPage({super.key});

  /// Mismo ritmo que cocina.js: rápido para que un pedido nuevo aparezca
  /// enseguida, sin saturar el wifi del local.
  static const intervalo = Duration(seconds: 4);

  @override
  State<CocinaPage> createState() => _CocinaPageState();
}

class _CocinaPageState extends State<CocinaPage> {
  late final CocinaRepo _repo = CocinaRepo(Servicios.leer(context).api);
  Timer? _timer;
  bool _consultando = false;

  List<ComandaCocina>? _comandas;
  Object? _errorInicial;
  bool _sinConexion = false;

  /// Pedidos marcados "Listo" que una consulta lanzada ANTES del cambio todavía
  /// puede traer de vuelta. Se filtran hasta que el servidor deja de mandarlos;
  /// sin esto la tarjeta reaparecería unos segundos después de tocar Listo.
  final Set<int> _entregadas = {};
  final Set<int> _enviando = {};

  @override
  void initState() {
    super.initState();
    _refrescar();
    _timer = Timer.periodic(CocinaPage.intervalo, (_) => _refrescar());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refrescar() async {
    // Con el wifi lento una consulta puede tardar más que el intervalo: no se
    // apilan pedidos al servidor uno detrás de otro.
    if (_consultando) return;
    _consultando = true;
    try {
      final nuevas = await _repo.pendientes();
      if (!mounted) return;
      _entregadas.retainAll(nuevas.map((c) => c.id));
      setState(() {
        _comandas = [
          for (final c in nuevas)
            if (!_entregadas.contains(c.id)) c,
        ];
        _errorInicial = null;
        _sinConexion = false;
      });
    } on ApiError catch (e) {
      if (!mounted) return;
      // Una falla pasajera no borra la pantalla: el cocinero sigue viendo los
      // pedidos que ya tenía mientras vuelve la conexión.
      setState(() {
        if (_comandas == null) _errorInicial = e;
        _sinConexion = true;
      });
    } finally {
      _consultando = false;
    }
  }

  Future<void> _reintentar() async {
    setState(() => _errorInicial = null);
    await _refrescar();
  }

  Future<void> _marcarListo(ComandaCocina c) async {
    if (_enviando.contains(c.id)) return;
    setState(() => _enviando.add(c.id));
    try {
      await _repo.marcarEntregada(c.id);
      if (!mounted) return;
      setState(() {
        _entregadas.add(c.id);
        _comandas = [
          for (final x in _comandas ?? const <ComandaCocina>[])
            if (x.id != c.id) x,
        ];
      });
      avisar(context, 'Comanda entregada', tipo: TipoAviso.exito);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _enviando.remove(c.id));
    }
  }

  Future<void> _reimprimir(ComandaCocina c) async {
    try {
      await _repo.reimprimir(c.id);
      if (mounted) {
        avisar(context, 'Pedido a la impresora', tipo: TipoAviso.exito);
      }
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final comandas = _comandas;
    if (_errorInicial != null) {
      return ErrorCarga(error: _errorInicial!, reintentar: _reintentar);
    }
    if (comandas == null) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _refrescar,
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          Contenido(
            ancho: 1200,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Encabezado(
                  titulo: 'Pedidos en cocina',
                  subtitulo: switch (comandas.length) {
                    0 => 'Se actualiza solo',
                    1 => '1 pedido · se actualiza solo',
                    final n => '$n pedidos · se actualiza solo',
                  },
                  accion: _sinConexion
                      ? const Pastilla(
                          'Sin conexión',
                          tipo: TipoEstado.peligro,
                          icono: Icons.wifi_off,
                        )
                      : null,
                ),
                if (comandas.isEmpty)
                  const Vacio(
                    icono: Icons.check_circle_outline,
                    titulo: 'Sin comandas pendientes',
                    mensaje: 'Los pedidos nuevos aparecen aquí solos.',
                  )
                else
                  _Grilla(
                    comandas: comandas,
                    enviando: _enviando,
                    alListo: _marcarListo,
                    alReimprimir: _reimprimir,
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// El riel de comandas: como en la cocina de verdad, cada pedido es una tira
/// de papel colgada en orden de llegada, el más antiguo a la izquierda. En el
/// celular las tiras van una debajo de otra, el más antiguo arriba.
class _Grilla extends StatelessWidget {
  const _Grilla({
    required this.comandas,
    required this.enviando,
    required this.alListo,
    required this.alReimprimir,
  });

  final List<ComandaCocina> comandas;
  final Set<int> enviando;
  final void Function(ComandaCocina) alListo;
  final void Function(ComandaCocina) alReimprimir;

  static const _anchoTira = 280.0;

  Widget _tira(ComandaCocina c) => ComandaImpresa(
    key: ValueKey(c.id),
    comanda: c,
    enviando: enviando.contains(c.id),
    alListo: () => alListo(c),
    alReimprimir: () => alReimprimir(c),
  );

  @override
  Widget build(BuildContext context) {
    final riel = Papel.de(context).riel;
    return LayoutBuilder(
      builder: (context, restr) {
        final enRiel = restr.maxWidth >= 640;
        return Container(
          decoration: BoxDecoration(
            color: riel,
            borderRadius: BorderRadius.circular(14),
          ),
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 18),
          child: enRiel
              ? SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      for (final c in comandas)
                        Padding(
                          padding: const EdgeInsets.only(right: 14),
                          child: SizedBox(width: _anchoTira, child: _tira(c)),
                        ),
                    ],
                  ),
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    for (final c in comandas)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 14),
                        child: _tira(c),
                      ),
                  ],
                ),
        );
      },
    );
  }
}

/// Una comanda como sale de la térmica: mesa en grande, hora de entrada, los
/// platos en mono y, abajo, cuánto lleva esperando.
class ComandaImpresa extends StatelessWidget {
  const ComandaImpresa({
    super.key,
    required this.comanda,
    required this.enviando,
    required this.alListo,
    required this.alReimprimir,
  });

  final ComandaCocina comanda;
  final bool enviando;
  final VoidCallback alListo;
  final VoidCallback alReimprimir;

  @override
  Widget build(BuildContext context) {
    final p = Papel.de(context);
    return TiraDePapel(
      marca: comanda.atrasada ? p.peligro : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Text(
                  comanda.rotulo,
                  style: impreso(tamano: 26, peso: FontWeight.w500),
                ),
              ),
              if (comanda.creadoEn != null)
                Text(
                  hora(comanda.creadoEn),
                  style: impreso(tamano: 14, color: p.tintaSuave),
                ),
            ],
          ),
          const Corte(),
          for (final pl in comanda.platos)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Text(
                '${pl.cantidad}x ${pl.nombre}',
                style: impreso(tamano: 16),
              ),
            ),
          const Corte(),
          CronometroComanda(
            minutos: comanda.minutos,
            atrasada: comanda.atrasada,
            limite: alertaMinutos,
          ),
          const SizedBox(height: 14),
          // Listo ocupa todo el ancho: se toca cientos de veces por turno.
          // Reimprimir va chico y aparte, debajo: confundirlos sacaría un
          // pedido de la pantalla por error.
          FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: p.exito,
              foregroundColor: Colors.white,
              disabledBackgroundColor: p.corte,
            ),
            onPressed: enviando ? null : alListo,
            icon: const Icon(Icons.check),
            label: const Text('Listo'),
          ),
          const SizedBox(height: 4),
          Center(
            child: TextButton.icon(
              style: TextButton.styleFrom(foregroundColor: p.tintaSuave),
              onPressed: alReimprimir,
              icon: const Icon(Icons.print_outlined, size: 18),
              label: const Text('Reimprimir'),
            ),
          ),
        ],
      ),
    );
  }
}
