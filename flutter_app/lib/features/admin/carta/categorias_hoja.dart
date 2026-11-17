import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'modelos.dart';
import 'repo.dart';

/// Catálogo de categorías de la carta: agregar (nombre + ícono) y eliminar.
/// Es un catálogo y no texto libre en cada plato para que "Cebiches",
/// "cebiches" y "Cebiche" no terminen siendo tres categorías distintas.
Future<void> abrirCategorias(
  BuildContext context,
  List<Categoria> categorias,
) => mostrarHoja<void>(context, (_) => _Categorias(categorias));

class _Categorias extends StatefulWidget {
  const _Categorias(this.iniciales);
  final List<Categoria> iniciales;

  @override
  State<_Categorias> createState() => _CategoriasState();
}

class _CategoriasState extends State<_Categorias> {
  final _nombre = TextEditingController();
  late List<Categoria> _categorias = widget.iniciales;
  String _icono = iconoPorDefecto;
  bool _ocupado = false;

  @override
  void dispose() {
    _nombre.dispose();
    super.dispose();
  }

  Future<void> _ejecutar(
    Future<void> Function(CartaRepo) accion,
    String ok,
  ) async {
    final repo = CartaRepo(Servicios.leer(context).api);
    setState(() => _ocupado = true);
    try {
      await accion(repo);
      final datos = await repo.cargar();
      if (!mounted) return;
      setState(() => _categorias = datos.categorias);
      avisar(context, ok, tipo: TipoAviso.exito);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _agregar() async {
    final nombre = _nombre.text.trim();
    if (nombre.isEmpty) {
      avisar(context, 'Escriba el nombre de la categoría');
      return;
    }
    await _ejecutar(
      (r) => r.crearCategoria(nombre, _icono),
      'Categoría creada',
    );
    if (!mounted) return;
    _nombre.clear();
    setState(() => _icono = iconoPorDefecto);
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final primario = Theme.of(context).colorScheme.primary;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Categorías de la carta',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
          ),
          const TituloSeccion('Ícono'),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final (valor, icono, titulo) in paletaIconos)
                Tooltip(
                  message: titulo,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(10),
                    onTap: () => setState(() => _icono = valor),
                    child: Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: _icono == valor ? primario : c.borde,
                          width: _icono == valor ? 2 : 1,
                        ),
                      ),
                      child: Icon(
                        icono,
                        color: _icono == valor ? primario : c.textoSuave,
                      ),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextField(
                  controller: _nombre,
                  maxLength: 50,
                  textCapitalization: TextCapitalization.words,
                  decoration: const InputDecoration(
                    labelText: 'Nueva categoría',
                    hintText: 'Ej: Postres',
                  ),
                  onSubmitted: (_) => _agregar(),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: _ocupado ? null : _agregar,
                child: const Text('Agregar'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (_categorias.isEmpty)
            Text(
              'Todavía no hay categorías. Agregue la primera arriba.',
              style: TextStyle(color: c.textoSuave),
            )
          else
            for (final cat in _categorias)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(iconoDe(cat.icono), color: c.textoSuave),
                title: Text(cat.nombre),
                trailing: IconButton(
                  tooltip: 'Eliminar',
                  color: c.peligro,
                  icon: const Icon(Icons.delete_outline),
                  onPressed: _ocupado
                      ? null
                      : () => _ejecutar(
                          (r) => r.eliminarCategoria(cat.id),
                          'Categoría eliminada',
                        ),
                ),
              ),
        ],
      ),
    );
  }
}
