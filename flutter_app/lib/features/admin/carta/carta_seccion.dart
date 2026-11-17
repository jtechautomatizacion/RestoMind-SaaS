import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/formato.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'categorias_hoja.dart';
import 'foto_plato.dart';
import 'formulario_plato.dart';
import 'modelos.dart';
import 'repo.dart';

/// Admin > Carta (CU-01): los platos agrupados por categoría con chips para
/// filtrar, alta y edición con foto, eliminación y el catálogo de categorías.
class CartaSeccion extends StatefulWidget {
  const CartaSeccion({super.key});

  @override
  State<CartaSeccion> createState() => _CartaSeccionState();
}

class _CartaSeccionState extends State<CartaSeccion> {
  /// null = "Todas".
  String? _filtro;

  /// Plato → momento en que cambió su foto en esta sesión (ver FotoPlato).
  final Map<int, int> _versionFoto = {};

  CartaRepo get _repo => CartaRepo(Servicios.leer(context).api);

  late Future<DatosCarta> _datos = _repo.cargar();

  /// Recarga sin vaciar la pantalla: FutureBuilder conserva los datos viejos
  /// mientras llegan los nuevos, así no salta el scroll.
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

  void _fotoCambiada(int platoId) =>
      _versionFoto[platoId] = DateTime.now().millisecondsSinceEpoch;

  Future<void> _abrirPlato(DatosCarta datos, [Plato? plato]) async {
    await abrirFormularioPlato(
      context,
      categorias: datos.categorias,
      plato: plato,
      alCambiarFoto: _fotoCambiada,
    );
    await _recargar();
  }

  Future<void> _abrirCategorias(DatosCarta datos) async {
    await abrirCategorias(context, datos.categorias);
    await _recargar();
  }

  Future<void> _eliminar(Plato plato) async {
    final ok = await confirmar(
      context,
      titulo: 'Eliminar plato',
      mensaje: '¿Quitar "${plato.nombre}" de la carta?',
      accion: 'Eliminar',
      peligrosa: true,
    );
    if (!ok || !mounted) return;
    try {
      final mensaje = await _repo.eliminarPlato(plato.id);
      if (!mounted) return;
      avisar(context, mensaje, tipo: TipoAviso.exito);
      await _recargar();
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<DatosCarta>(
    future: _datos,
    builder: (context, s) {
      if (s.hasError) {
        return ErrorCarga(error: s.error!, reintentar: _recargar);
      }
      final datos = s.data;
      if (datos == null) {
        return const Center(child: CircularProgressIndicator());
      }
      final enUso = categoriasEnUso(datos.platos);
      // Un filtro que ya no existe (se eliminó su último plato) vuelve a "Todas".
      final filtro = enUso.contains(_filtro) ? _filtro : null;
      final visibles = filtrarPorCategoria(datos.platos, filtro);
      return RefreshIndicator(
        onRefresh: _recargar,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: () => _abrirPlato(datos),
                  icon: const Icon(Icons.add),
                  label: const Text('Nuevo plato'),
                ),
                OutlinedButton.icon(
                  onPressed: () => _abrirCategorias(datos),
                  icon: const Icon(Icons.sell_outlined),
                  label: const Text('Categorías'),
                ),
              ],
            ),
            const SizedBox(height: 12),
            // Con una sola categoría en uso, filtrar no ayuda a encontrar nada.
            if (enUso.length > 1)
              _ChipsCategorias(
                categorias: enUso,
                seleccionada: filtro,
                iconoDe: datos.iconoDeCategoria,
                elegir: (c) => setState(() => _filtro = c),
              ),
            if (datos.platos.isEmpty)
              const Vacio(
                icono: Icons.restaurant_menu,
                titulo: 'Su carta está vacía',
                mensaje: 'Cree una categoría y luego agregue sus platos.',
              )
            else
              for (final p in visibles)
                _FilaPlato(
                  plato: p,
                  version: _versionFoto[p.id],
                  editar: () => _abrirPlato(datos, p),
                  eliminar: () => _eliminar(p),
                ),
          ],
        ),
      );
    },
  );
}

class _ChipsCategorias extends StatelessWidget {
  const _ChipsCategorias({
    required this.categorias,
    required this.seleccionada,
    required this.iconoDe,
    required this.elegir,
  });

  final List<String> categorias;
  final String? seleccionada;
  final IconData Function(String) iconoDe;
  final ValueChanged<String?> elegir;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          ChoiceChip(
            label: const Text('Todas'),
            selected: seleccionada == null,
            onSelected: (_) => elegir(null),
          ),
          for (final c in categorias)
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: ChoiceChip(
                avatar: Icon(iconoDe(c), size: 18),
                label: Text(c),
                selected: seleccionada == c,
                onSelected: (_) => elegir(c),
              ),
            ),
        ],
      ),
    ),
  );
}

class _FilaPlato extends StatelessWidget {
  const _FilaPlato({
    required this.plato,
    required this.version,
    required this.editar,
    required this.eliminar,
  });

  final Plato plato;
  final int? version;
  final VoidCallback editar;
  final VoidCallback eliminar;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        child: ListTile(
          contentPadding: const EdgeInsets.fromLTRB(12, 6, 4, 6),
          leading: FotoPlato(url: plato.imagenUrl, version: version),
          title: Text(
            plato.nombre,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          subtitle: Text.rich(
            TextSpan(
              children: [
                TextSpan(text: '${plato.categoria} · '),
                TextSpan(
                  text: soles(plato.precioVenta),
                  style: TextStyle(
                    color: c.dinero,
                    fontWeight: FontWeight.w700,
                    fontFeatures: cifras,
                  ),
                ),
              ],
            ),
          ),
          onTap: editar,
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
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
          ),
        ),
      ),
    );
  }
}
