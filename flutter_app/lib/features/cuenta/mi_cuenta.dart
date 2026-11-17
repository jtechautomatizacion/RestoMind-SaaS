import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/config.dart';
import '../../core/servicios.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';

/// Mi cuenta: quién soy, de qué restaurante, qué versión, y cambiar mi
/// contraseña. Cambiarla cierra TODAS las sesiones (también esta): hay que
/// volver a entrar con la nueva.
Future<void> mostrarMiCuenta(BuildContext context) =>
    mostrarHoja<void>(context, (_) => const _MiCuenta());

class _MiCuenta extends StatefulWidget {
  const _MiCuenta();

  @override
  State<_MiCuenta> createState() => _MiCuentaState();
}

class _MiCuentaState extends State<_MiCuenta> {
  final _form = GlobalKey<FormState>();
  final _actual = TextEditingController();
  final _nueva = TextEditingController();
  final _repetir = TextEditingController();
  bool _guardando = false;

  @override
  void dispose() {
    _actual.dispose();
    _nueva.dispose();
    _repetir.dispose();
    super.dispose();
  }

  Future<void> _cambiar() async {
    if (!_form.currentState!.validate()) return;
    final s = Servicios.leer(context);
    setState(() => _guardando = true);
    try {
      await s.api.patch('/usuarios/me/password', {
        'password_actual': _actual.text,
        'nueva_password': _nueva.text,
      });
      if (!mounted) return;
      Navigator.pop(context);
      s.sesion.contrasenaCambiada();
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final u = Servicios.de(context).sesion.usuario!;
    final c = Colores.de(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              u.nombre,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            Text(
              '${u.etiquetaRoles} · ${u.clienteNombre}',
              style: TextStyle(color: c.textoSuave),
            ),
            if (u.email != u.nombre)
              Text(u.email, style: TextStyle(color: c.textoSuave)),
            const TituloSeccion('Cambiar contraseña'),
            TextFormField(
              controller: _actual,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Contraseña actual'),
              validator: (v) =>
                  (v ?? '').isEmpty ? 'Escriba su contraseña actual' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _nueva,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Nueva contraseña',
                helperText: 'Mínimo 6 caracteres',
              ),
              validator: (v) =>
                  (v ?? '').length < 6 ? 'Use al menos 6 caracteres' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _repetir,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Repita la nueva contraseña',
              ),
              validator: (v) =>
                  v != _nueva.text ? 'No coincide con la nueva' : null,
            ),
            const SizedBox(height: 8),
            Text(
              'Al cambiarla se cierra la sesión en todos sus aparatos.',
              style: TextStyle(color: c.textoSuave, fontSize: 12),
            ),
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _guardando ? null : _cambiar,
              child: Text(_guardando ? 'Guardando…' : 'Cambiar contraseña'),
            ),
            const SizedBox(height: 16),
            Text(
              'ver. $versionApp',
              textAlign: TextAlign.center,
              style: TextStyle(color: c.textoSuave, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
