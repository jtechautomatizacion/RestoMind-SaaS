import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'modelos.dart';
import 'repo.dart';

/// Pone una contraseña nueva a una cuenta. El backend cierra todas las
/// sesiones de esa cuenta: quien la use tiene que volver a entrar.
/// Devuelve true si se guardó.
Future<bool> mostrarResetearPassword(BuildContext context, Miembro m) async =>
    await mostrarHoja<bool>(context, (_) => _ResetearPassword(miembro: m)) ??
    false;

class _ResetearPassword extends StatefulWidget {
  const _ResetearPassword({required this.miembro});

  final Miembro miembro;

  @override
  State<_ResetearPassword> createState() => _ResetearPasswordState();
}

class _ResetearPasswordState extends State<_ResetearPassword> {
  final _form = GlobalKey<FormState>();
  final _password = TextEditingController();
  bool _guardando = false;

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  Future<void> _guardar() async {
    if (!_form.currentState!.validate()) return;
    final repo = PersonalRepo(Servicios.leer(context).api);
    setState(() => _guardando = true);
    try {
      await repo.resetearPassword(widget.miembro.id, _password.text);
      if (mounted) Navigator.pop(context, true);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final m = widget.miembro;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Resetear contraseña',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 4),
            Text(
              'Cuenta: ${m.nombre} (${m.acceso})',
              style: TextStyle(color: Colores.de(context).textoSuave),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _password,
              maxLength: 200,
              decoration: const InputDecoration(
                labelText: 'Nueva contraseña',
                helperText: 'Mínimo 6 caracteres',
              ),
              validator: (v) =>
                  (v ?? '').length < 6 ? 'Use al menos 6 caracteres' : null,
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _guardando ? null : _guardar,
              child: Text(
                _guardando ? 'Guardando…' : 'Guardar nueva contraseña',
              ),
            ),
          ],
        ),
      ),
    );
  }
}
