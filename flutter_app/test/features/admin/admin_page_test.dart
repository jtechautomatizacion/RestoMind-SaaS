import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/features/admin/admin_page.dart';
import 'package:restomind/features/admin/caja/caja_seccion.dart';
import 'package:restomind/features/admin/carta/carta_seccion.dart';
import 'package:restomind/features/admin/personal/personal_seccion.dart';

import '../../apoyo.dart';

/// Respuestas neutras para cualquier sección: listas vacías y una caja
/// cerrada sin historial.
ApiFalsa _api() => ApiFalsa((req) {
  return switch (req.url.path) {
    '/api/caja/estado' => (200, {'hay_caja_abierta': false, 'turnos_hoy': 0}),
    '/api/caja/gate' => (200, {'hay_caja_abierta': false}),
    _ => (200, <Object>[]),
  };
});

void main() {
  testWidgets('sin sección pedida abre Carta', (tester) async {
    await montar(tester, const AdminPage(), api: _api());
    await tester.pumpAndSettle();

    expect(find.byType(CartaSeccion), findsOneWidget);
    expect(find.byType(PersonalSeccion), findsNothing);
  });

  testWidgets('abre la sección pedida y solo carga esa', (tester) async {
    final api = _api();
    await montar(tester, const AdminPage(seccion: 'personal'), api: api);
    await tester.pumpAndSettle();

    expect(find.byType(PersonalSeccion), findsOneWidget);
    expect(api.llamadas('GET', '/usuarios'), hasLength(1));
    expect(api.llamadas('GET', '/caja/estado'), isEmpty);
  });

  testWidgets('las sub-pestañas van en el orden de siempre', (tester) async {
    await montar(tester, const AdminPage(), api: _api());
    await tester.pumpAndSettle();

    final titulos = tester
        .widgetList<Tab>(find.byType(Tab))
        .map((t) => ((t.child! as Row).children.last as Text).data)
        .toList();
    expect(titulos, ['Carta', 'Gastos', 'Personal', 'Boletas', 'Caja']);
  });

  testWidgets('tocar una sub-pestaña cambia de sección', (tester) async {
    final api = _api();
    await montar(tester, const AdminPage(seccion: 'personal'), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Caja'));
    await tester.pumpAndSettle();

    expect(find.byType(CajaSeccion), findsOneWidget);
    expect(find.byType(PersonalSeccion), findsNothing);
    expect(api.llamadas('GET', '/caja/estado'), hasLength(1));
  });
}
