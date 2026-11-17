import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/formato.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'modelos.dart';
import 'repo.dart';

/// Historial de un insumo en un panel lateral, no en una hoja que tapa todo:
/// el admin sigue viendo la tabla de stock al costado mientras revisa.
/// [alCambiar] avisa que el stock cambió (se deshizo algo).
Future<void> abrirHistorial(
  BuildContext context,
  Insumo insumo, {
  required VoidCallback alCambiar,
}) => showGeneralDialog<void>(
  context: context,
  barrierDismissible: true,
  barrierLabel: 'Cerrar historial',
  transitionDuration: const Duration(milliseconds: 200),
  pageBuilder: (ctx, _, _) => Align(
    alignment: Alignment.centerRight,
    child: SizedBox(
      width: math.min(420, MediaQuery.sizeOf(ctx).width),
      height: double.infinity,
      child: Material(
        child: SafeArea(
          child: _Historial(insumo: insumo, alCambiar: alCambiar),
        ),
      ),
    ),
  ),
  transitionBuilder: (_, animacion, _, hijo) => SlideTransition(
    position: Tween(
      begin: const Offset(1, 0),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: animacion, curve: Curves.easeOutCubic)),
    child: hijo,
  ),
);

class _Historial extends StatefulWidget {
  const _Historial({required this.insumo, required this.alCambiar});
  final Insumo insumo;
  final VoidCallback alCambiar;

  @override
  State<_Historial> createState() => _HistorialState();
}

class _HistorialState extends State<_Historial> {
  late Future<List<Movimiento>> _movimientos = _cargar();
  late double _stock = widget.insumo.cantidadActual;

  /// Movimiento que se está deshaciendo. Mientras haya uno, TODOS los botones
  /// quedan apagados: dos toques seguidos descontarían dos veces.
  int? _deshaciendo;

  GastosRepo get _repo => GastosRepo(Servicios.leer(context).api);

  Future<List<Movimiento>> _cargar() => _repo.historial(widget.insumo.id);

  void _recargar() => setState(() {
    _movimientos = _cargar();
  });

  Future<void> _deshacer(Movimiento m) async {
    if (_deshaciendo != null) return;
    setState(() => _deshaciendo = m.id);
    final ok = await confirmar(
      context,
      titulo: 'Deshacer movimiento',
      mensaje:
          'El original queda registrado y se agrega otro que lo corrige. '
          '¿Continuar?',
      accion: 'Deshacer',
    );
    if (!mounted) return;
    if (!ok) {
      setState(() => _deshaciendo = null);
      return;
    }
    try {
      final inverso = await _repo.revertir(widget.insumo.id, m.id);
      if (!mounted) return;
      // El inverso trae el stock ya corregido: no hace falta pedir el insumo.
      _stock = inverso.saldoDespues;
      _recargar();
      avisar(context, 'Movimiento deshecho', tipo: TipoAviso.exito);
      widget.alCambiar();
    } on ApiError catch (e) {
      // P. ej. deshacer una entrada cuando ese stock ya se consumió: el
      // backend no deja el saldo en negativo y lo explica.
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _deshaciendo = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final insumo = widget.insumo;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 8, 8),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      insumo.nombre,
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    Text(
                      '${cantidad(_stock)} ${insumo.unidad} en stock',
                      style: TextStyle(color: c.textoSuave),
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Cerrar',
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
        ),
        const Divider(),
        Expanded(
          child: FutureBuilder<List<Movimiento>>(
            future: _movimientos,
            builder: (context, s) {
              if (s.hasError) {
                return ErrorCarga(error: s.error!, reintentar: _recargar);
              }
              final movimientos = s.data;
              if (movimientos == null) {
                return const Center(child: CircularProgressIndicator());
              }
              return movimientos.isEmpty
                  ? ListView(
                      children: const [
                        Vacio(
                          icono: Icons.history,
                          titulo: 'Sin movimientos todavía',
                          mensaje:
                              'Las entradas y salidas que registre aparecen acá.',
                        ),
                      ],
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      itemCount: movimientos.length,
                      separatorBuilder: (_, _) => const Divider(),
                      itemBuilder: (_, i) => _FilaMovimiento(
                        movimiento: movimientos[i],
                        unidad: insumo.unidad,
                        deshacer: _deshaciendo == null
                            ? () => _deshacer(movimientos[i])
                            : null,
                      ),
                    );
            },
          ),
        ),
      ],
    );
  }
}

class _FilaMovimiento extends StatelessWidget {
  const _FilaMovimiento({
    required this.movimiento,
    required this.unidad,
    required this.deshacer,
  });

  final Movimiento movimiento;
  final String unidad;

  /// null = botón apagado (hay otro deshaciéndose).
  final VoidCallback? deshacer;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final m = movimiento;
    final entrada = m.tipo == TipoMovimiento.entrada;
    final color = entrada ? c.exito : c.aviso;
    final tachado = m.revertido
        ? const TextStyle(decoration: TextDecoration.lineThrough)
        : null;
    final meta = [
      etiquetaRazon(m.razon),
      if (m.fecha != null) fecha(m.fecha),
      if (m.usuarioNombre case final n? when n.isNotEmpty) n,
    ].join(' · ');
    return Opacity(
      opacity: m.revertido ? .5 : 1,
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: entrada ? c.exitoFondo : c.avisoFondo,
          child: Icon(entrada ? Icons.north : Icons.south, color: color),
        ),
        title: Text.rich(
          TextSpan(
            children: [
              TextSpan(
                text: '${m.tipo.signo}${cantidad(m.cantidad)} $unidad',
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              TextSpan(
                text: '  →  ${cantidad(m.saldoDespues)} $unidad',
                style: TextStyle(color: c.textoSuave),
              ),
            ],
          ),
          style: tachado,
        ),
        subtitle: Text(meta),
        trailing: m.puedeDeshacer
            ? IconButton(
                tooltip: 'Deshacer este movimiento',
                icon: const Icon(Icons.undo),
                onPressed: deshacer,
              )
            : null,
      ),
    );
  }
}
