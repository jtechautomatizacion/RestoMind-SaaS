import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_error.dart';
import '../../core/config.dart';
import '../../core/servicios.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';

/// Ingreso con dos caminos: el DUEÑO entra con email y contraseña; el PERSONAL
/// con el código de 6 dígitos que le dio el dueño (Admin > Personal).
class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.alternarTema});

  final VoidCallback alternarTema;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _form = GlobalKey<FormState>();
  final _usuario = TextEditingController();
  final _password = TextEditingController();
  bool _esPersonal = false;
  bool _entrando = false;
  bool _verPassword = false;
  String? _error;

  @override
  void dispose() {
    _usuario.dispose();
    _password.dispose();
    super.dispose();
  }

  void _cambiarModo(bool personal) {
    setState(() {
      _esPersonal = personal;
      _error = null;
      _usuario.clear();
    });
  }

  Future<void> _entrar() async {
    if (!_form.currentState!.validate()) return;
    final s = Servicios.leer(context);
    setState(() {
      _entrando = true;
      _error = null;
    });
    try {
      final u = _esPersonal
          ? await s.sesion.entrarConCodigo(_usuario.text.trim(), _password.text)
          : await s.sesion.entrarConEmail(
              _usuario.text.trim().toLowerCase(),
              _password.text,
            );
      if (u.esSuperadmin && mounted) {
        // El panel general es otra página con su propio ingreso.
        s.plataforma.irA('/static/superadmin.html');
      }
    } on ApiError catch (e) {
      setState(() => _error = e.mensaje);
    } finally {
      if (mounted) setState(() => _entrando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final aviso = Servicios.de(context).sesion.avisoSalida;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Align(
                    alignment: Alignment.centerRight,
                    child: IconButton(
                      tooltip: 'Cambiar tema',
                      onPressed: widget.alternarTema,
                      icon: Icon(
                        Theme.of(context).brightness == Brightness.dark
                            ? Icons.light_mode_outlined
                            : Icons.dark_mode_outlined,
                      ),
                    ),
                  ),
                  Image.asset(
                    'assets/marca/marca-blanca.png',
                    height: 72,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'RestoMind',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
                  ),
                  Text(
                    'Ingrese para empezar el turno',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: c.textoSuave),
                  ),
                  const SizedBox(height: 24),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Form(
                        key: _form,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            SegmentedButton<bool>(
                              segments: const [
                                ButtonSegment(
                                  value: false,
                                  icon: Icon(Icons.person_outline),
                                  label: Text('Administrador'),
                                ),
                                ButtonSegment(
                                  value: true,
                                  icon: Icon(Icons.groups_outlined),
                                  label: Text('Personal'),
                                ),
                              ],
                              selected: {_esPersonal},
                              onSelectionChanged: (v) => _cambiarModo(v.first),
                            ),
                            const SizedBox(height: 20),
                            if (aviso != null && _error == null) ...[
                              Pastilla(
                                aviso,
                                tipo: TipoEstado.aviso,
                                icono: Icons.info_outline,
                              ),
                              const SizedBox(height: 14),
                            ],
                            TextFormField(
                              key: ValueKey(_esPersonal),
                              controller: _usuario,
                              autofocus: true,
                              keyboardType: _esPersonal
                                  ? TextInputType.number
                                  : TextInputType.emailAddress,
                              autofillHints: _esPersonal
                                  ? null
                                  : const [AutofillHints.email],
                              inputFormatters: _esPersonal
                                  ? [
                                      FilteringTextInputFormatter.digitsOnly,
                                      LengthLimitingTextInputFormatter(6),
                                    ]
                                  : null,
                              decoration: InputDecoration(
                                labelText: _esPersonal
                                    ? 'Código de acceso'
                                    : 'Email',
                                helperText: _esPersonal
                                    ? 'Los 6 dígitos que le dio el administrador'
                                    : null,
                                prefixIcon: Icon(
                                  _esPersonal
                                      ? Icons.pin_outlined
                                      : Icons.mail_outline,
                                ),
                              ),
                              validator: (v) {
                                final t = (v ?? '').trim();
                                if (t.isEmpty) {
                                  return _esPersonal
                                      ? 'Escriba su código'
                                      : 'Escriba su email';
                                }
                                if (_esPersonal && t.length != 6) {
                                  return 'El código tiene 6 dígitos';
                                }
                                return null;
                              },
                            ),
                            const SizedBox(height: 14),
                            TextFormField(
                              controller: _password,
                              obscureText: !_verPassword,
                              autofillHints: const [AutofillHints.password],
                              onFieldSubmitted: (_) => _entrar(),
                              decoration: InputDecoration(
                                labelText: 'Contraseña',
                                prefixIcon: const Icon(Icons.lock_outline),
                                suffixIcon: IconButton(
                                  tooltip: _verPassword ? 'Ocultar' : 'Mostrar',
                                  onPressed: () => setState(
                                    () => _verPassword = !_verPassword,
                                  ),
                                  icon: Icon(
                                    _verPassword
                                        ? Icons.visibility_off_outlined
                                        : Icons.visibility_outlined,
                                  ),
                                ),
                              ),
                              validator: (v) => (v ?? '').isEmpty
                                  ? 'Escriba su contraseña'
                                  : null,
                            ),
                            if (_error != null) ...[
                              const SizedBox(height: 14),
                              Text(
                                _error!,
                                style: TextStyle(
                                  color: c.peligro,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                            const SizedBox(height: 20),
                            FilledButton(
                              onPressed: _entrando ? null : _entrar,
                              child: Text(
                                _entrando ? 'Ingresando…' : 'Ingresar',
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
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
          ),
        ),
      ),
    );
  }
}
