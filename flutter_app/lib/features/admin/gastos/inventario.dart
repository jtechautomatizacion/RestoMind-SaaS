import 'package:flutter/material.dart';

import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'formulario_insumo.dart';
import 'formulario_movimiento.dart';
import 'historial_insumo.dart';
import 'modelos.dart';

/// Inventario dentro de Gastos, no en una pestaña propia: el admin ya entra
/// acá cuando llega mercadería. Arranca cerrado para no empujar la lista de
/// gastos fuera de la pantalla en un celular; cerrado muestra solo el resumen.
class BloqueInventario extends StatefulWidget {
  const BloqueInventario({
    super.key,
    required this.insumos,
    required this.alCambiar,
  });

  final List<Insumo> insumos;

  /// Se llama al cerrar cualquier hoja del inventario, para recargar el stock.
  final Future<void> Function() alCambiar;

  @override
  State<BloqueInventario> createState() => _BloqueInventarioState();
}

class _BloqueInventarioState extends State<BloqueInventario> {
  bool _abierto = false;

  Future<void> _tras(Future<void> hoja) async {
    await hoja;
    await widget.alCambiar();
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final resumen = resumenInventario(widget.insumos);
    final alertas = enAlerta(widget.insumos);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ListTile(
            leading: const Icon(Icons.inventory_2_outlined),
            title: const Text(
              'Inventario',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (resumen != null) Pastilla(resumen.$1, tipo: resumen.$2),
                const SizedBox(width: 4),
                Icon(_abierto ? Icons.expand_less : Icons.expand_more),
              ],
            ),
            onTap: () => setState(() => _abierto = !_abierto),
          ),
          if (_abierto) ...[
            const Divider(),
            if (alertas.isNotEmpty) _Alertas(alertas),
            if (widget.insumos.isEmpty)
              Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'Todavía no hay insumos. Agregue los que más le importan '
                  '(pescado, limón, ají…).',
                  style: TextStyle(color: c.textoSuave),
                ),
              )
            else
              for (final i in widget.insumos)
                _FilaInsumo(
                  insumo: i,
                  movimiento: (tipo) =>
                      _tras(abrirFormularioMovimiento(context, i, tipo)),
                  historial: () => abrirHistorial(
                    context,
                    i,
                    alCambiar: () => widget.alCambiar(),
                  ),
                  editar: () =>
                      _tras(abrirFormularioInsumo(context, insumo: i)),
                ),
            Padding(
              padding: const EdgeInsets.all(12),
              child: OutlinedButton.icon(
                onPressed: () => _tras(abrirFormularioInsumo(context)),
                icon: const Icon(Icons.add),
                label: const Text('Agregar insumo'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _Alertas extends StatelessWidget {
  const _Alertas(this.insumos);
  final List<Insumo> insumos;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: c.superficieAlt,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final i in insumos)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                children: [
                  Pastilla(i.estado.etiqueta, tipo: i.estado.tipo),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: i.nombre,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          TextSpan(
                            text:
                                '  ${i.stock} · mín ${cantidad(i.cantidadMinima)}',
                            style: TextStyle(color: c.textoSuave),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _FilaInsumo extends StatelessWidget {
  const _FilaInsumo({
    required this.insumo,
    required this.movimiento,
    required this.historial,
    required this.editar,
  });

  final Insumo insumo;
  final void Function(TipoMovimiento) movimiento;
  final VoidCallback historial;
  final VoidCallback editar;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final i = insumo;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
      child: Wrap(
        alignment: WrapAlignment.spaceBetween,
        crossAxisAlignment: WrapCrossAlignment.center,
        runSpacing: 4,
        children: [
          ConstrainedBox(
            constraints: const BoxConstraints(minWidth: 180),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        i.nombre,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Pastilla(i.estado.etiqueta, tipo: i.estado.tipo),
                  ],
                ),
                Text(
                  '${i.stock} · mín ${cantidad(i.cantidadMinima)}',
                  style: TextStyle(color: c.textoSuave, fontFeatures: cifras),
                ),
              ],
            ),
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                tooltip: 'Registrar entrada',
                color: c.exito,
                icon: const Icon(Icons.north),
                onPressed: () => movimiento(TipoMovimiento.entrada),
              ),
              IconButton(
                tooltip: 'Registrar salida',
                color: c.aviso,
                icon: const Icon(Icons.south),
                onPressed: () => movimiento(TipoMovimiento.salida),
              ),
              IconButton(
                tooltip: 'Ver movimientos',
                icon: const Icon(Icons.history),
                onPressed: historial,
              ),
              IconButton(
                tooltip: 'Editar',
                icon: const Icon(Icons.edit_outlined),
                onPressed: editar,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
