import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/formato.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'formulario_gasto.dart';
import 'inventario.dart';
import 'modelos.dart';
import 'repo.dart';

/// Admin > Gastos (CU-04): caja chica agrupada por día, y el inventario.
class GastosSeccion extends StatefulWidget {
  const GastosSeccion({super.key});

  @override
  State<GastosSeccion> createState() => _GastosSeccionState();
}

class _GastosSeccionState extends State<GastosSeccion> {
  GastosRepo get _repo => GastosRepo(Servicios.leer(context).api);

  late Future<DatosGastos> _datos = _repo.cargar();

  /// Recarga sin vaciar la pantalla: FutureBuilder conserva los datos viejos
  /// mientras llegan los nuevos, así no se cierra el inventario ni salta el
  /// scroll.
  Future<void> _recargar() async {
    final f = _repo.cargar();
    setState(() {
      _datos = f;
    });
    try {
      await f;
    } on ApiError {
      // El error se muestra en el build.
    }
  }

  Future<void> _abrirGasto([Compra? compra]) async {
    await abrirFormularioGasto(context, compra: compra);
    await _recargar();
  }

  Future<void> _eliminar(Compra compra) async {
    final ok = await confirmar(
      context,
      titulo: 'Eliminar gasto',
      mensaje: '¿Eliminar "${compra.descripcion}" (${soles(compra.monto)})?',
      accion: 'Eliminar',
      peligrosa: true,
    );
    if (!ok || !mounted) return;
    await _ejecutar(() => _repo.eliminarCompra(compra.id), 'Gasto eliminado');
  }

  /// Anular no pide confirmación: se deshace con "Restaurar".
  Future<void> _alternarAnulado(Compra compra) => _ejecutar(
    () => _repo.cambiarEstadoCompra(compra.id, anular: compra.registrado),
    compra.registrado ? 'Gasto anulado' : 'Gasto restaurado',
  );

  Future<void> _ejecutar(Future<void> Function() accion, String ok) async {
    try {
      await accion();
      if (!mounted) return;
      avisar(context, ok, tipo: TipoAviso.exito);
      await _recargar();
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<DatosGastos>(
    future: _datos,
    builder: (context, s) {
      if (s.hasError) {
        return ErrorCarga(error: s.error!, reintentar: _recargar);
      }
      final datos = s.data;
      if (datos == null) {
        return const Center(child: CircularProgressIndicator());
      }
      final hoy = fechaIso(DateTime.now());
      return RefreshIndicator(
        onRefresh: _recargar,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.icon(
                onPressed: () => _abrirGasto(),
                icon: const Icon(Icons.add),
                label: const Text('Registrar gasto'),
              ),
            ),
            const SizedBox(height: 12),
            BloqueInventario(insumos: datos.insumos, alCambiar: _recargar),
            if (datos.compras.isEmpty)
              const Vacio(
                icono: Icons.receipt_long_outlined,
                titulo: 'Todavía no hay gastos',
                mensaje: 'Registre aquí lo que sale de la caja chica.',
              )
            else
              for (final dia in agruparPorDia(datos.compras)) ...[
                _TituloDia(dia),
                for (final compra in dia.compras)
                  _FilaGasto(
                    compra: compra,
                    // Editar y eliminar solo hoy (igual que el backend): un
                    // gasto de otro día se anula, no se borra.
                    esDeHoy: compra.fecha == hoy,
                    editar: () => _abrirGasto(compra),
                    eliminar: () => _eliminar(compra),
                    alternarAnulado: () => _alternarAnulado(compra),
                  ),
              ],
          ],
        ),
      );
    },
  );
}

class _TituloDia extends StatelessWidget {
  const _TituloDia(this.dia);
  final DiaDeGastos dia;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final estilo = TextStyle(
      color: c.textoSuave,
      fontWeight: FontWeight.w700,
      fontSize: 13,
      fontFeatures: cifras,
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 18, 4, 8),
      child: Row(
        children: [
          Expanded(child: Text(fechaDeCalendario(dia.fecha), style: estilo)),
          Text(soles(dia.total), style: estilo),
        ],
      ),
    );
  }
}

class _FilaGasto extends StatelessWidget {
  const _FilaGasto({
    required this.compra,
    required this.esDeHoy,
    required this.editar,
    required this.eliminar,
    required this.alternarAnulado,
  });

  final Compra compra;
  final bool esDeHoy;
  final VoidCallback editar;
  final VoidCallback eliminar;
  final VoidCallback alternarAnulado;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final vigente = compra.registrado;
    final tachado = vigente
        ? null
        : const TextStyle(decoration: TextDecoration.lineThrough);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Opacity(
        opacity: vigente ? 1 : .55,
        child: Card(
          child: ListTile(
            contentPadding: const EdgeInsets.fromLTRB(16, 4, 4, 4),
            title: Text(
              compra.descripcion,
              style: const TextStyle(
                fontWeight: FontWeight.w700,
              ).merge(tachado),
            ),
            subtitle: Row(
              children: [
                Flexible(
                  child: Text('${compra.categoria ?? 'Sin categoría'} · '),
                ),
                Text(
                  soles(compra.monto),
                  style: const TextStyle(
                    fontFeatures: cifras,
                    fontWeight: FontWeight.w700,
                  ).merge(tachado),
                ),
                if (!vigente) ...[
                  const SizedBox(width: 8),
                  const Pastilla('Anulado'),
                ],
              ],
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (esDeHoy && vigente) ...[
                  IconButton(
                    tooltip: 'Editar',
                    icon: const Icon(Icons.edit_outlined),
                    onPressed: editar,
                  ),
                  IconButton(
                    tooltip: 'Eliminar',
                    color: c.peligro,
                    icon: const Icon(Icons.delete_outline),
                    onPressed: eliminar,
                  ),
                ],
                IconButton(
                  tooltip: vigente ? 'Anular' : 'Restaurar',
                  color: vigente ? c.peligro : null,
                  icon: Icon(vigente ? Icons.block : Icons.restore),
                  onPressed: alternarAnulado,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
