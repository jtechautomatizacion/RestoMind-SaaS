import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'modelos.dart';
import 'repo.dart';

/// Alta o edición de un insumo. Eliminar vive acá y no en la fila: al lado de
/// los botones de entrada y salida que se usan a diario, un toque equivocado
/// borraría el insumo con todo su historial.
Future<void> abrirFormularioInsumo(BuildContext context, {Insumo? insumo}) =>
    mostrarHoja<void>(context, (_) => _FormularioInsumo(insumo));

class _FormularioInsumo extends StatefulWidget {
  const _FormularioInsumo(this.insumo);
  final Insumo? insumo;

  @override
  State<_FormularioInsumo> createState() => _FormularioInsumoState();
}

class _FormularioInsumoState extends State<_FormularioInsumo> {
  final _form = GlobalKey<FormState>();
  late final _nombre = TextEditingController(text: widget.insumo?.nombre);
  late final _actual = TextEditingController(
    text: widget.insumo == null
        ? null
        : cantidad(widget.insumo!.cantidadActual),
  );
  late final _minima = TextEditingController(
    text: widget.insumo == null
        ? null
        : cantidad(widget.insumo!.cantidadMinima),
  );
  late String _unidad = widget.insumo?.unidad ?? unidades.first.$1;
  bool _ocupado = false;

  bool get _editando => widget.insumo != null;

  @override
  void dispose() {
    _nombre.dispose();
    _actual.dispose();
    _minima.dispose();
    super.dispose();
  }

  Future<void> _ejecutar(
    Future<void> Function(GastosRepo) accion,
    String ok,
  ) async {
    final repo = GastosRepo(Servicios.leer(context).api);
    setState(() => _ocupado = true);
    try {
      await accion(repo);
      if (!mounted) return;
      avisar(context, ok, tipo: TipoAviso.exito);
      Navigator.pop(context);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _guardar() async {
    if (!_form.currentState!.validate()) return;
    final b = BorradorInsumo(
      nombre: _nombre.text.trim(),
      unidad: _unidad,
      cantidadActual: leerCantidad(_actual.text)!,
      cantidadMinima: leerCantidad(_minima.text)!,
    );
    final id = widget.insumo?.id;
    await _ejecutar(
      (r) => id == null ? r.crearInsumo(b) : r.editarInsumo(id, b),
      id == null ? 'Insumo agregado' : 'Insumo actualizado',
    );
  }

  Future<void> _eliminar() async {
    final insumo = widget.insumo!;
    // Avisa que se lleva el historial: es lo que el admin no espera.
    final ok = await confirmar(
      context,
      titulo: 'Eliminar insumo',
      mensaje:
          '¿Eliminar "${insumo.nombre}" del inventario? '
          'Se borran también todos sus movimientos registrados.',
      accion: 'Eliminar',
      peligrosa: true,
    );
    if (!ok || !mounted) return;
    await _ejecutar((r) => r.eliminarInsumo(insumo.id), 'Insumo eliminado');
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _editando ? 'Editar insumo' : 'Nuevo insumo',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _nombre,
              maxLength: 60,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Insumo',
                hintText: 'Ej: Pescado fresco',
              ),
              validator: (v) =>
                  (v ?? '').trim().isEmpty ? 'Escriba el nombre' : null,
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<String>(
              initialValue: _unidad,
              decoration: const InputDecoration(labelText: 'Unidad'),
              items: [
                for (final (valor, etiqueta) in unidades)
                  DropdownMenuItem(value: valor, child: Text(etiqueta)),
              ],
              onChanged: (v) => setState(() => _unidad = v ?? _unidad),
            ),
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: _CampoCantidad(
                    controller: _actual,
                    etiqueta: 'Stock actual',
                    // Cero vale: se acabó, pero el insumo sigue en la lista.
                    aceptaCero: true,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _CampoCantidad(
                    controller: _minima,
                    etiqueta: 'Stock mínimo',
                    // Un mínimo de cero nunca avisaría nada.
                    aceptaCero: false,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Se le avisa cuando el stock baje del mínimo.',
              style: TextStyle(color: c.textoSuave, fontSize: 12),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _ocupado ? null : _guardar,
              child: Text(_ocupado ? 'Guardando…' : 'Guardar'),
            ),
            if (_editando)
              TextButton(
                onPressed: _ocupado ? null : _eliminar,
                style: TextButton.styleFrom(foregroundColor: c.peligro),
                child: const Text('Eliminar este insumo'),
              ),
          ],
        ),
      ),
    );
  }
}

/// Cantidad con hasta dos decimales, nunca negativa.
class _CampoCantidad extends StatelessWidget {
  const _CampoCantidad({
    required this.controller,
    required this.etiqueta,
    required this.aceptaCero,
  });

  final TextEditingController controller;
  final String etiqueta;
  final bool aceptaCero;

  @override
  Widget build(BuildContext context) => TextFormField(
    controller: controller,
    keyboardType: const TextInputType.numberWithOptions(decimal: true),
    decoration: InputDecoration(labelText: etiqueta),
    validator: (v) {
      final n = leerCantidad(v ?? '');
      if (n == null) return 'Número con hasta dos decimales';
      if (!aceptaCero && n <= 0) return 'Debe ser mayor a 0';
      return null;
    },
  );
}
