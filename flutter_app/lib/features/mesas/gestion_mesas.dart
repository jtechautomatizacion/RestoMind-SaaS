import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_error.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';
import 'modelos.dart';
import 'sala.dart';

/// Crear, editar y eliminar mesas (solo admin; el backend lo exige igual).
Future<void> abrirGestionMesas(BuildContext context, Sala sala) =>
    mostrarHoja<void>(context, (_) => _GestionMesas(sala));

class _GestionMesas extends StatelessWidget {
  const _GestionMesas(this.sala);

  final Sala sala;

  Future<void> _eliminar(BuildContext context, Mesa mesa) async {
    if (!await confirmar(
      context,
      titulo: 'Eliminar la mesa ${mesa.numero}',
      mensaje: 'No se puede deshacer.',
      accion: 'Eliminar',
      peligrosa: true,
    )) {
      return;
    }
    try {
      await sala.repo.eliminarMesa(mesa.id);
      if (context.mounted) {
        avisar(context, 'Mesa eliminada', tipo: TipoAviso.exito);
      }
      await sala.refrescar();
    } on ApiError catch (e) {
      if (context.mounted) avisar(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return ListenableBuilder(
      listenable: sala,
      builder: (context, _) => SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Encabezado(
              titulo: 'Gestionar mesas',
              accion: FilledButton.icon(
                onPressed: () => _formularioMesa(context, sala),
                icon: const Icon(Icons.add),
                label: const Text('Nueva mesa'),
              ),
            ),
            if (sala.mesas.isEmpty)
              const Vacio(
                icono: Icons.table_restaurant_outlined,
                titulo: 'Aún no hay mesas',
                mensaje: 'Cree la primera con "Nueva mesa".',
              ),
            for (final m in sala.mesas)
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.table_restaurant_outlined),
                title: Text(
                  'Mesa ${m.numero}',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(
                  [
                    '${m.capacidad} personas',
                    if (m.ubicacion != null && m.ubicacion!.isNotEmpty)
                      m.ubicacion!,
                    m.ocupada ? 'ocupada' : 'libre',
                  ].join(' · '),
                  style: TextStyle(color: c.textoSuave),
                ),
                trailing: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      tooltip: 'Editar',
                      onPressed: () => _formularioMesa(context, sala, m),
                      icon: const Icon(Icons.edit_outlined),
                    ),
                    IconButton(
                      tooltip: 'Eliminar',
                      color: c.peligro,
                      onPressed: () => _eliminar(context, m),
                      icon: const Icon(Icons.delete_outline),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

Future<void> _formularioMesa(BuildContext context, Sala sala, [Mesa? mesa]) =>
    showDialog<void>(
      context: context,
      builder: (_) => _FormularioMesa(sala: sala, mesa: mesa),
    );

class _FormularioMesa extends StatefulWidget {
  const _FormularioMesa({required this.sala, this.mesa});

  final Sala sala;
  final Mesa? mesa;

  @override
  State<_FormularioMesa> createState() => _FormularioMesaState();
}

class _FormularioMesaState extends State<_FormularioMesa> {
  final _form = GlobalKey<FormState>();
  late final _numero = TextEditingController(
    text: widget.mesa == null ? '' : '${widget.mesa!.numero}',
  );
  late final _capacidad = TextEditingController(
    text: '${widget.mesa?.capacidad ?? 4}',
  );
  late final _ubicacion = TextEditingController(
    text: widget.mesa?.ubicacion ?? '',
  );
  bool _guardando = false;

  @override
  void dispose() {
    _numero.dispose();
    _capacidad.dispose();
    _ubicacion.dispose();
    super.dispose();
  }

  String? _entero(String? v, {required int max}) {
    final n = int.tryParse(v ?? '');
    if (n == null || n < 1) return 'Escriba un número mayor que cero.';
    if (n > max) return 'Máximo $max.';
    return null;
  }

  Future<void> _guardar() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _guardando = true);
    try {
      final ubicacion = _ubicacion.text.trim();
      await widget.sala.repo.guardarMesa(
        id: widget.mesa?.id,
        numero: int.parse(_numero.text),
        capacidad: int.parse(_capacidad.text),
        ubicacion: ubicacion.isEmpty ? null : ubicacion,
      );
      if (!mounted) return;
      avisar(
        context,
        widget.mesa == null ? 'Mesa creada' : 'Mesa actualizada',
        tipo: TipoAviso.exito,
      );
      Navigator.pop(context);
      await widget.sala.refrescar();
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final digitos = [FilteringTextInputFormatter.digitsOnly];
    return AlertDialog(
      title: Text(
        widget.mesa == null
            ? 'Nueva mesa'
            : 'Editar mesa ${widget.mesa!.numero}',
      ),
      content: Form(
        key: _form,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              controller: _numero,
              autofocus: widget.mesa == null,
              keyboardType: TextInputType.number,
              inputFormatters: digitos,
              decoration: const InputDecoration(labelText: 'Número de mesa'),
              validator: (v) => _entero(v, max: 9999),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _capacidad,
              keyboardType: TextInputType.number,
              inputFormatters: digitos,
              decoration: const InputDecoration(
                labelText: 'Capacidad (personas)',
              ),
              validator: (v) => _entero(v, max: 50),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _ubicacion,
              maxLength: 50,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Ubicación (opcional)',
                hintText: 'Patio, Interior...',
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          onPressed: _guardando ? null : _guardar,
          child: const Text('Guardar'),
        ),
      ],
    );
  }
}
