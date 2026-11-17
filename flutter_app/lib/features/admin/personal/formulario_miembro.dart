import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/roles.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'modelos.dart';
import 'repo.dart';

/// Hoja para crear o editar una cuenta. Hace la llamada ella misma para que,
/// si la API rechaza algo, el formulario siga abierto con lo escrito.
///
/// Al crear devuelve la cuenta nueva (trae el código de acceso generado); al
/// editar devuelve la misma [editando] como señal de "se guardó".
Future<Miembro?> mostrarFormularioMiembro(
  BuildContext context, {
  Miembro? editando,
}) => mostrarHoja<Miembro>(
  context,
  (_) => _FormularioMiembro(editando: editando),
);

class _FormularioMiembro extends StatefulWidget {
  const _FormularioMiembro({this.editando});

  final Miembro? editando;

  @override
  State<_FormularioMiembro> createState() => _FormularioMiembroState();
}

class _FormularioMiembroState extends State<_FormularioMiembro> {
  final _form = GlobalKey<FormState>();
  late final _nombre = TextEditingController(text: widget.editando?.nombre);
  final _password = TextEditingController();
  late final Set<String> _roles = {
    ...?widget.editando?.roles.where(rolesPersonal.contains),
  };
  late bool _activo = widget.editando?.activo ?? true;
  bool _guardando = false;

  bool get _creando => widget.editando == null;
  bool get _esAdmin => widget.editando?.esAdmin ?? false;

  @override
  void dispose() {
    _nombre.dispose();
    _password.dispose();
    super.dispose();
  }

  void _alternarRol(String rol, bool marcado) => setState(() {
    marcado ? _roles.add(rol) : _roles.remove(rol);
  });

  Future<void> _guardar() async {
    if (!_form.currentState!.validate()) return;
    if (!_esAdmin && _roles.isEmpty) {
      avisar(context, 'Marque al menos un rol', tipo: TipoAviso.error);
      return;
    }
    final repo = PersonalRepo(Servicios.leer(context).api);
    final roles = [
      for (final r in rolesPersonal)
        if (_roles.contains(r)) r,
    ];
    setState(() => _guardando = true);
    try {
      final Miembro resultado;
      if (_creando) {
        resultado = await repo.crear(
          nombre: _nombre.text.trim(),
          password: _password.text,
          roles: roles,
        );
      } else {
        final m = widget.editando!;
        // Los roles y el estado del admin son fijos: no se mandan.
        await repo.editar(
          m.id,
          nombre: _nombre.text.trim(),
          roles: _esAdmin ? null : roles,
          activo: _esAdmin ? null : _activo,
        );
        resultado = m;
      }
      if (mounted) Navigator.pop(context, resultado);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final m = widget.editando;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _creando ? 'Nueva cuenta' : 'Editar cuenta',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _nombre,
              textCapitalization: TextCapitalization.words,
              maxLength: 100,
              decoration: const InputDecoration(labelText: 'Nombre'),
              validator: (v) =>
                  (v ?? '').trim().isEmpty ? 'Escriba el nombre' : null,
            ),
            if (_creando) ...[
              Text(
                'El código de acceso se genera solo al guardar. No hace '
                'falta un celular.',
                style: TextStyle(color: c.textoSuave, fontSize: 13),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _password,
                maxLength: 200,
                decoration: const InputDecoration(
                  labelText: 'Contraseña',
                  helperText: 'Mínimo 6 caracteres',
                ),
                validator: (v) =>
                    (v ?? '').length < 6 ? 'Use al menos 6 caracteres' : null,
              ),
            ] else if (_esAdmin) ...[
              _CampoFijo(etiqueta: 'Email de acceso', valor: m!.acceso),
              const _CampoFijo(
                etiqueta: 'Rol',
                valor: 'Administrador (no editable)',
              ),
            ] else
              _CampoFijo(etiqueta: 'Código de acceso', valor: m!.acceso),
            if (!_esAdmin) ...[
              const TituloSeccion('Roles'),
              for (final rol in rolesPersonal)
                _InterruptorRol(
                  rol: rol,
                  marcado: _roles.contains(rol),
                  bloqueado: rolBloqueado(rol, _roles),
                  alCambiar: (v) => _alternarRol(rol, v),
                ),
            ],
            if (!_creando && !_esAdmin) ...[
              const SizedBox(height: 8),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Cuenta activa'),
                subtitle: const Text(
                  'Desactivada no puede entrar, pero no se borra.',
                ),
                value: _activo,
                onChanged: (v) => setState(() => _activo = v),
              ),
            ],
            const SizedBox(height: 16),
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

class _InterruptorRol extends StatelessWidget {
  const _InterruptorRol({
    required this.rol,
    required this.marcado,
    required this.bloqueado,
    required this.alCambiar,
  });

  final String rol;
  final bool marcado;
  final bool bloqueado;
  final ValueChanged<bool> alCambiar;

  @override
  Widget build(BuildContext context) => SwitchListTile(
    key: ValueKey('rol-$rol'),
    contentPadding: EdgeInsets.zero,
    title: Text(etiquetaRol[rol] ?? rol),
    subtitle: rolesExclusivos.contains(rol)
        ? const Text(
            'Atiende solo: mesas, cocina y cobro en una pantalla. '
            'No se combina con otros roles.',
          )
        : null,
    value: marcado,
    onChanged: bloqueado ? null : alCambiar,
  );
}

class _CampoFijo extends StatelessWidget {
  const _CampoFijo({required this.etiqueta, required this.valor});

  final String etiqueta;
  final String valor;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(etiqueta, style: TextStyle(color: c.textoSuave, fontSize: 12)),
          const SizedBox(height: 2),
          // Mismo motivo que en el diálogo de "Cuenta creada": SelectableText
          // llega vacío al lector de pantalla si no lleva su etiqueta.
          Semantics(
            label: '$etiqueta $valor',
            excludeSemantics: true,
            child: SelectableText(
              valor,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
