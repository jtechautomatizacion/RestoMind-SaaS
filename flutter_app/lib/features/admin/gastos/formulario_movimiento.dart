import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'campo_fecha.dart';
import 'modelos.dart';
import 'repo.dart';

/// Entrada o salida de stock. El tipo NO es un campo: lo fija el botón que
/// abrió la hoja, así nadie anota una salida creyendo que es una entrada.
Future<void> abrirFormularioMovimiento(
  BuildContext context,
  Insumo insumo,
  TipoMovimiento tipo,
) => mostrarHoja<void>(context, (_) => _FormularioMovimiento(insumo, tipo));

class _FormularioMovimiento extends StatefulWidget {
  const _FormularioMovimiento(this.insumo, this.tipo);
  final Insumo insumo;
  final TipoMovimiento tipo;

  @override
  State<_FormularioMovimiento> createState() => _FormularioMovimientoState();
}

class _FormularioMovimientoState extends State<_FormularioMovimiento> {
  final _form = GlobalKey<FormState>();
  final _cantidad = TextEditingController();

  /// El motivo más probable: quien anota una entrada casi siempre está
  /// registrando mercadería que acaba de llegar.
  late String _razon = _esEntrada ? 'compra' : 'uso';
  DateTime _fecha = DateTime.now();
  bool _guardando = false;

  bool get _esEntrada => widget.tipo == TipoMovimiento.entrada;
  String get _titulo => _esEntrada ? 'Registrar entrada' : 'Registrar salida';

  @override
  void dispose() {
    _cantidad.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    if (!_form.currentState!.validate()) return;
    final insumo = widget.insumo;
    setState(() => _guardando = true);
    try {
      final mov = await GastosRepo(Servicios.leer(context).api)
          .registrarMovimiento(
            insumo.id,
            tipo: widget.tipo,
            cantidad: leerCantidad(_cantidad.text)!,
            razon: _razon,
            fecha: _fecha,
          );
      if (!mounted) return;
      final u = insumo.unidad;
      avisar(
        context,
        '${mov.tipo.signo}${cantidad(mov.cantidad)} $u · '
        'quedan ${cantidad(mov.saldoDespues)} $u',
        tipo: TipoAviso.exito,
      );
      Navigator.pop(context);
    } on ApiError catch (e) {
      // Una salida mayor al stock la rechaza el backend con su mensaje.
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final insumo = widget.insumo;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _titulo,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 4),
            Text.rich(
              TextSpan(
                children: [
                  TextSpan(
                    text: insumo.nombre,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                  TextSpan(text: ' · quedan ${insumo.stock}'),
                ],
              ),
              style: TextStyle(color: c.textoSuave),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _cantidad,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: InputDecoration(
                labelText: 'Cantidad',
                hintText: '5',
                suffixText: insumo.unidad,
              ),
              validator: (v) {
                final n = leerCantidad(v ?? '');
                return n == null || n <= 0
                    ? 'Escriba una cantidad mayor a 0'
                    : null;
              },
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: _razon,
              decoration: const InputDecoration(labelText: 'Motivo'),
              items: [
                for (final (valor, etiqueta) in razonesMovimiento)
                  DropdownMenuItem(value: valor, child: Text(etiqueta)),
              ],
              onChanged: (v) => setState(() => _razon = v ?? _razon),
            ),
            const SizedBox(height: 16),
            CampoFecha(
              valor: _fecha,
              cambiar: (f) => setState(() => _fecha = f),
            ),
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: _guardando ? null : _guardar,
              icon: Icon(_esEntrada ? Icons.north : Icons.south),
              label: Text(_guardando ? 'Guardando…' : _titulo),
            ),
          ],
        ),
      ),
    );
  }
}
