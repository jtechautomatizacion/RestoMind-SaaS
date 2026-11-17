import 'package:flutter/material.dart';

import '../../design/tema.dart';
import 'boletas/boletas_seccion.dart';
import 'caja/caja_seccion.dart';
import 'carta/carta_seccion.dart';
import 'gastos/gastos_seccion.dart';
import 'personal/personal_seccion.dart';

/// Administración: Carta, Gastos, Personal, Boletas y Caja, en sub-pestañas.
///
/// Solo se arma la sección visible, y se vuelve a armar al entrar: Boletas y
/// Caja cambian por cosas que pasan en otras pantallas (un cobro, una boleta
/// que falló), así que mostrarlas con lo que se cargó antes sería engañoso.
class AdminPage extends StatefulWidget {
  const AdminPage({super.key, this.seccion});

  /// 'carta', 'gastos', 'personal', 'boletas' o 'caja'. Por defecto, 'carta'.
  final String? seccion;

  @override
  State<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage>
    with SingleTickerProviderStateMixin {
  static const _secciones = [
    ('carta', 'Carta', Icons.restaurant_menu),
    ('gastos', 'Gastos', Icons.shopping_bag_outlined),
    ('personal', 'Personal', Icons.group_outlined),
    ('boletas', 'Boletas', Icons.receipt_long_outlined),
    ('caja', 'Caja', Icons.point_of_sale),
  ];

  late final TabController _pestanas = TabController(
    length: _secciones.length,
    initialIndex: _secciones
        .indexWhere((s) => s.$1 == widget.seccion)
        .clamp(0, _secciones.length - 1),
    vsync: this,
  )..addListener(() => setState(() {}));

  @override
  void dispose() {
    _pestanas.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Column(
      children: [
        Material(
          color: c.superficie,
          child: TabBar(
            controller: _pestanas,
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            dividerColor: c.borde,
            tabs: [
              for (final (_, titulo, icono) in _secciones)
                Tab(
                  height: 52,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(icono, size: 18),
                      const SizedBox(width: 6),
                      Text(titulo),
                    ],
                  ),
                ),
            ],
          ),
        ),
        Expanded(
          child: KeyedSubtree(
            key: ValueKey(_pestanas.index),
            child: switch (_secciones[_pestanas.index].$1) {
              'gastos' => const GastosSeccion(),
              'personal' => const PersonalSeccion(),
              'boletas' => const BoletasSeccion(),
              'caja' => const CajaSeccion(),
              _ => const CartaSeccion(),
            },
          ),
        ),
      ],
    );
  }
}
