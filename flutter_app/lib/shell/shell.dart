import 'package:flutter/material.dart';

import '../core/roles.dart';
import '../core/servicios.dart';
import '../design/tema.dart';
import '../design/widgets.dart';
import '../features/admin/admin_page.dart';
import '../features/cocina/cocina_page.dart';
import '../features/cuenta/mi_cuenta.dart';
import '../features/dinero/dinero_page.dart';
import '../features/mesas/mesas_page.dart';
import 'caja_gate.dart';

/// Lo que una pantalla puede pedirle al marco de la app.
class ShellScope extends InheritedWidget {
  const ShellScope({
    super.key,
    required this.ir,
    required this.cajaGate,
    required super.child,
  });

  /// Cambia de pestaña. En Admin, [seccion] abre una sección concreta
  /// ('carta', 'gastos', 'personal', 'boletas', 'caja').
  final void Function(Pestana pestana, {String? seccion}) ir;
  final CajaGate cajaGate;

  static ShellScope de(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ShellScope>()!;

  static ShellScope leer(BuildContext context) =>
      context.getInheritedWidgetOfExactType<ShellScope>()!;

  @override
  bool updateShouldNotify(ShellScope oldWidget) => false;
}

class Shell extends StatefulWidget {
  const Shell({super.key, required this.alternarTema});

  final VoidCallback alternarTema;

  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  late final CajaGate _gate = CajaGate(Servicios.leer(context).api)..iniciar();
  Pestana? _actual;
  String? _seccionAdmin;

  static const _iconos = {
    Pestana.mesas: (Icons.grid_view_outlined, Icons.grid_view_rounded, 'Mesas'),
    Pestana.cocina: (
      Icons.local_fire_department_outlined,
      Icons.local_fire_department,
      'Cocina',
    ),
    Pestana.dinero: (
      Icons.bar_chart_outlined,
      Icons.bar_chart_rounded,
      'Dinero',
    ),
    Pestana.admin: (Icons.tune_outlined, Icons.tune, 'Admin'),
  };

  static const _titulos = {
    Pestana.mesas: 'Mesas',
    Pestana.cocina: 'Cocina',
    Pestana.dinero: 'Su dinero',
    Pestana.admin: 'Administración',
  };

  @override
  void dispose() {
    _gate.dispose();
    super.dispose();
  }

  void _ir(Pestana p, {String? seccion}) {
    setState(() {
      _actual = p;
      _seccionAdmin = seccion;
    });
    if (p == Pestana.mesas || p == Pestana.cocina) _gate.refrescar();
  }

  @override
  Widget build(BuildContext context) {
    final s = Servicios.de(context);
    final usuario = s.sesion.usuario!;
    final pestanas = usuario.pestanas;
    final actual = pestanas.contains(_actual) ? _actual! : pestanas.first;
    final ancho = MediaQuery.sizeOf(context).width;
    final rail = ancho >= 900 && pestanas.length > 1;
    final c = Colores.de(context);

    final cuerpo = ListenableBuilder(
      listenable: _gate,
      builder: (context, _) {
        final bloqueada =
            (actual == Pestana.mesas || actual == Pestana.cocina) &&
            _gate.abierta == false;
        if (bloqueada) {
          return _CajaCerrada(
            esAdmin: usuario.esAdmin,
            irACaja: () => _ir(Pestana.admin, seccion: 'caja'),
          );
        }
        return KeyedSubtree(
          key: ValueKey('$actual-$_seccionAdmin'),
          child: switch (actual) {
            Pestana.mesas => const MesasPage(),
            Pestana.cocina => const CocinaPage(),
            Pestana.dinero => const DineroPage(),
            Pestana.admin => AdminPage(seccion: _seccionAdmin),
          },
        );
      },
    );

    return ShellScope(
      ir: _ir,
      cajaGate: _gate,
      child: Scaffold(
        appBar: AppBar(
          titleSpacing: 12,
          title: Row(
            children: [
              const _Logo(),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      usuario.clienteNombre,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      '${_titulos[actual]} · ${usuario.etiquetaRoles}',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: c.textoSuave,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          actions: [
            IconButton(
              tooltip: 'Cambiar tema',
              onPressed: widget.alternarTema,
              icon: Icon(
                Theme.of(context).brightness == Brightness.dark
                    ? Icons.light_mode_outlined
                    : Icons.dark_mode_outlined,
              ),
            ),
            IconButton(
              tooltip: 'Mi cuenta',
              onPressed: () => mostrarMiCuenta(context),
              icon: const Icon(Icons.person_outline),
            ),
            IconButton(
              tooltip: 'Cerrar sesión',
              onPressed: () async {
                if (await confirmar(
                  context,
                  titulo: 'Cerrar sesión',
                  mensaje: 'Se cerrará la sesión en este aparato.',
                  accion: 'Salir',
                )) {
                  await s.sesion.salir();
                }
              },
              icon: const Icon(Icons.logout),
            ),
            const SizedBox(width: 4),
          ],
        ),
        body: rail
            ? Row(
                children: [
                  NavigationRail(
                    selectedIndex: pestanas.indexOf(actual),
                    onDestinationSelected: (i) => _ir(pestanas[i]),
                    labelType: NavigationRailLabelType.all,
                    backgroundColor: c.superficie,
                    indicatorColor: Theme.of(
                      context,
                    ).colorScheme.secondaryContainer,
                    destinations: [
                      for (final p in pestanas)
                        NavigationRailDestination(
                          icon: Icon(_iconos[p]!.$1),
                          selectedIcon: Icon(_iconos[p]!.$2),
                          label: Text(_iconos[p]!.$3),
                        ),
                    ],
                  ),
                  VerticalDivider(width: 1, color: c.borde),
                  Expanded(child: cuerpo),
                ],
              )
            : cuerpo,
        bottomNavigationBar: rail || pestanas.length < 2
            ? null
            : NavigationBar(
                selectedIndex: pestanas.indexOf(actual),
                onDestinationSelected: (i) => _ir(pestanas[i]),
                destinations: [
                  for (final p in pestanas)
                    NavigationDestination(
                      icon: Icon(_iconos[p]!.$1),
                      selectedIcon: Icon(_iconos[p]!.$2),
                      label: _iconos[p]!.$3,
                    ),
                ],
              ),
      ),
    );
  }
}

class _Logo extends StatelessWidget {
  const _Logo();

  @override
  Widget build(BuildContext context) => Container(
    width: 32,
    height: 32,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      borderRadius: BorderRadius.circular(10),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFFA8C9FA), Color(0xFF7FB0F2), Color(0xFF5C93DC)],
        stops: [0, .55, 1],
      ),
    ),
    child: const Text(
      'R',
      style: TextStyle(
        color: Color(0xFF0A2440),
        fontWeight: FontWeight.w800,
        fontSize: 16,
      ),
    ),
  );
}

class _CajaCerrada extends StatelessWidget {
  const _CajaCerrada({required this.esAdmin, required this.irACaja});

  final bool esAdmin;
  final VoidCallback irACaja;

  @override
  Widget build(BuildContext context) => Vacio(
    icono: Icons.lock_outline,
    titulo: 'Caja cerrada',
    mensaje: esAdmin
        ? 'Abra la caja del día para empezar a tomar pedidos.'
        : 'No se pueden tomar pedidos hasta que el administrador abra la caja del día.',
    accion: esAdmin
        ? FilledButton.icon(
            onPressed: irACaja,
            icon: const Icon(Icons.point_of_sale),
            label: const Text('Ir a Caja'),
          )
        : null,
  );
}
