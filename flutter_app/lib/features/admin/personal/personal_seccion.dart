import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'formulario_miembro.dart';
import 'modelos.dart';
import 'repo.dart';
import 'resetear_password.dart';

/// Admin > Personal: las cuentas del restaurante, cada una con su login.
///
/// El switch "Avisarme de comandas nuevas" de la versión HTML no está acá:
/// suena y vibra en el aparato con la app abierta, y eso vive con Cocina, no
/// con la cuenta.
class PersonalSeccion extends StatefulWidget {
  const PersonalSeccion({super.key});

  @override
  State<PersonalSeccion> createState() => _PersonalSeccionState();
}

class _PersonalSeccionState extends State<PersonalSeccion> {
  late final _repo = PersonalRepo(Servicios.leer(context).api);

  /// Recarga conservando lo que ya se ve mientras llegan los datos nuevos.
  final _cargador = GlobalKey<CargadorState<List<Miembro>>>();

  void _recargar() => _cargador.currentState?.recargar();

  Future<void> _crear() async {
    final creado = await mostrarFormularioMiembro(context);
    if (creado == null || !mounted) return;
    _recargar();
    await _mostrarCodigo(creado);
  }

  /// El código lo genera el backend: sin mostrarlo acá, el admin no sabría
  /// qué darle al empleado. Va en un diálogo y no en un aviso que se esfuma,
  /// porque hay que copiarlo o anotarlo.
  Future<void> _mostrarCodigo(Miembro m) => showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Cuenta creada'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Entréguele a ${m.nombre} este código de acceso:'),
          const SizedBox(height: 12),
          Center(
            // SelectableText llega al lector de pantalla como un campo vacío:
            // sin esta etiqueta, justo el código no se anunciaba.
            child: Semantics(
              label: 'Código de acceso ${m.celular ?? ''}',
              excludeSemantics: true,
              child: SelectableText(
                m.celular ?? '',
                style: const TextStyle(
                  fontFamily: fuenteMono,
                  fontSize: 34,
                  fontWeight: FontWeight.w500,
                  letterSpacing: 6,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Entra con ese código y la contraseña que usted le puso. '
            'El código también queda en la lista de Personal.',
          ),
        ],
      ),
      actions: [
        FilledButton(
          onPressed: () => Navigator.pop(ctx),
          child: const Text('Listo'),
        ),
      ],
    ),
  );

  Future<void> _editar(Miembro m) async {
    final guardado = await mostrarFormularioMiembro(context, editando: m);
    if (guardado == null || !mounted) return;
    avisar(context, 'Cuenta actualizada', tipo: TipoAviso.exito);
    _recargar();
  }

  Future<void> _resetear(Miembro m) async {
    if (!await mostrarResetearPassword(context, m) || !mounted) return;
    avisar(context, 'Contraseña actualizada', tipo: TipoAviso.exito);
  }

  Future<void> _eliminar(Miembro m) async {
    final ok = await confirmar(
      context,
      titulo: 'Eliminar cuenta',
      mensaje: '¿Eliminar la cuenta de "${m.nombre}"? No se puede deshacer.',
      accion: 'Eliminar',
      peligrosa: true,
    );
    if (!ok || !mounted) return;
    try {
      await _repo.eliminar(m.id);
      if (!mounted) return;
      avisar(context, 'Cuenta eliminada', tipo: TipoAviso.exito);
      _recargar();
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final miEmail = Servicios.de(context).sesion.usuario?.email;
    return Cargador<List<Miembro>>(
      key: _cargador,
      cargar: _repo.listar,
      construir: (context, personal, _) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Contenido(
            ancho: 760,
            padding: EdgeInsets.zero,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Encabezado(
                  titulo: 'Personal',
                  subtitulo: 'Cada persona entra con su propio código.',
                  accion: FilledButton.icon(
                    onPressed: _crear,
                    icon: const Icon(Icons.person_add_alt_1),
                    label: const Text('Nueva cuenta'),
                  ),
                ),
                if (personal.isEmpty)
                  const Vacio(
                    icono: Icons.group_outlined,
                    titulo: 'Aún no registra personal',
                    mensaje: 'Cree una cuenta para cada mozo, cajero o cocina.',
                  ),
                for (final m in personal)
                  _FilaMiembro(
                    miembro: m,
                    esUnoMismo: m.email != null && m.email == miEmail,
                    alEditar: () => _editar(m),
                    alResetear: () => _resetear(m),
                    alEliminar: () => _eliminar(m),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _FilaMiembro extends StatelessWidget {
  const _FilaMiembro({
    required this.miembro,
    required this.esUnoMismo,
    required this.alEditar,
    required this.alResetear,
    required this.alEliminar,
  });

  final Miembro miembro;
  final bool esUnoMismo;
  final VoidCallback alEditar;
  final VoidCallback alResetear;
  final VoidCallback alEliminar;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final m = miembro;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Opacity(
        opacity: m.activo ? 1 : .6,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 6, 10),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: 8,
                        runSpacing: 4,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Text(
                            m.nombre,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          if (esUnoMismo)
                            const Pastilla('Tú', tipo: TipoEstado.info),
                          if (!m.activo) const Pastilla('Desactivada'),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        m.etiquetaRoles,
                        style: TextStyle(color: c.textoSuave, fontSize: 13),
                      ),
                      const SizedBox(height: 2),
                      if (m.esAdmin)
                        Text(
                          m.acceso,
                          style: TextStyle(color: c.textoSuave, fontSize: 13),
                        )
                      else
                        Text.rich(
                          TextSpan(
                            children: [
                              TextSpan(
                                text: 'Código ',
                                style: TextStyle(color: c.textoSuave),
                              ),
                              TextSpan(
                                text: m.acceso,
                                style: const TextStyle(
                                  fontFamily: fuenteMono,
                                  fontWeight: FontWeight.w500,
                                  letterSpacing: 2,
                                ),
                              ),
                            ],
                          ),
                          style: const TextStyle(fontSize: 14),
                        ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Editar',
                  onPressed: alEditar,
                  icon: const Icon(Icons.edit_outlined),
                ),
                IconButton(
                  tooltip: 'Resetear contraseña',
                  onPressed: alResetear,
                  icon: const Icon(Icons.key_outlined),
                ),
                // Nadie se elimina a sí mismo: el restaurante se quedaría sin
                // admin. El backend también lo rechaza.
                if (!esUnoMismo)
                  IconButton(
                    tooltip: 'Eliminar',
                    onPressed: alEliminar,
                    color: c.peligro,
                    icon: const Icon(Icons.delete_outline),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
