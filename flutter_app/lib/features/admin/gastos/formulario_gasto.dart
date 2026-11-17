import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/servicios.dart';
import '../../../design/widgets.dart';
import 'campo_fecha.dart';
import 'modelos.dart';
import 'repo.dart';

/// Registrar un gasto nuevo ([compra] null) o editar uno de hoy.
Future<void> abrirFormularioGasto(BuildContext context, {Compra? compra}) =>
    mostrarHoja<void>(context, (_) => _FormularioGasto(compra));

class _FormularioGasto extends StatefulWidget {
  const _FormularioGasto(this.compra);
  final Compra? compra;

  @override
  State<_FormularioGasto> createState() => _FormularioGastoState();
}

class _FormularioGastoState extends State<_FormularioGasto> {
  final _form = GlobalKey<FormState>();
  late final _descripcion = TextEditingController(
    text: widget.compra?.descripcion,
  );
  late final _monto = TextEditingController(
    text: widget.compra?.monto.toStringAsFixed(2),
  );
  late String? _categoria = widget.compra?.categoria;
  late DateTime _fecha =
      DateTime.tryParse(widget.compra?.fecha ?? '') ?? DateTime.now();
  String? _errorFecha;
  bool _guardando = false;

  bool get _editando => widget.compra != null;

  /// Un gasto viejo con una categoría que ya no se ofrece la conserva.
  List<String> get _categorias => [
    ...categoriasGasto,
    if (_categoria != null && !categoriasGasto.contains(_categoria))
      _categoria!,
  ];

  @override
  void dispose() {
    _descripcion.dispose();
    _monto.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    final errorFecha = errorFechaGasto(_fecha);
    setState(() => _errorFecha = errorFecha);
    if (!_form.currentState!.validate() || errorFecha != null) return;
    final repo = GastosRepo(Servicios.leer(context).api);
    final borrador = BorradorCompra(
      descripcion: _descripcion.text.trim(),
      categoria: _categoria,
      monto: leerCantidad(_monto.text) ?? 0,
      fecha: _fecha,
    );
    setState(() => _guardando = true);
    try {
      if (_editando) {
        await repo.editarCompra(widget.compra!.id, borrador);
      } else {
        await repo.crearCompra(borrador);
      }
      if (!mounted) return;
      avisar(
        context,
        _editando ? 'Gasto actualizado' : 'Gasto registrado',
        tipo: TipoAviso.exito,
      );
      Navigator.pop(context);
    } on ApiError catch (e) {
      // Incluye la regla del día: solo se editan gastos de hoy (403).
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _editando ? 'Editar gasto' : 'Registrar gasto',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _descripcion,
              maxLength: 100,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Descripción',
                hintText: 'Ej: Pescado del mercado',
              ),
              validator: (v) =>
                  (v ?? '').trim().isEmpty ? 'Escriba qué se compró' : null,
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<String?>(
              initialValue: _categoria,
              decoration: const InputDecoration(labelText: 'Categoría'),
              items: [
                const DropdownMenuItem(child: Text('Sin categoría')),
                for (final cat in _categorias)
                  DropdownMenuItem(value: cat, child: Text(cat)),
              ],
              onChanged: (v) => setState(() => _categoria = v),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _monto,
              enabled: !_editando,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: InputDecoration(
                labelText: 'Monto',
                prefixText: 'S/ ',
                hintText: '85.50',
                // El monto no se edita: cambiarlo descuadraría la caja de ese
                // día. Se anula el gasto y se registra otro.
                helperText: _editando
                    ? 'No se puede cambiar. Anule este gasto y registre otro.'
                    : null,
              ),
              validator: (v) {
                if (_editando) return null;
                final m = leerCantidad(v ?? '');
                return m == null || m <= 0
                    ? 'Escriba un monto mayor a 0, con hasta dos decimales'
                    : null;
              },
            ),
            const SizedBox(height: 16),
            CampoFecha(
              valor: _fecha,
              error: _errorFecha,
              cambiar: (f) => setState(() {
                _fecha = f;
                _errorFecha = null;
              }),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _guardando ? null : _guardar,
              child: Text(_guardando ? 'Guardando…' : 'Guardar'),
            ),
          ],
        ),
      ),
    );
  }
}
