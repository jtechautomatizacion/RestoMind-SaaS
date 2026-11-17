import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/features/mesas/mesas_page.dart';

import '../../apoyo.dart';
import '../mesas/backend_falso.dart';

/// La 1 y la 12 libres, la 2 en cocina, la 3 esperando la cuenta, y un pedido
/// para llevar en cocina.
BackendSala _sala() => BackendSala()
  ..mesas = [
    mesa(1, 1),
    mesa(2, 2, ocupada: true, cuenta: 45),
    mesa(3, 3, ocupada: true, cuenta: 95),
    mesa(12, 12),
  ]
  ..cocina = [enCocina(20, 2), enCocina(21, 0)]
  ..comandas = [comanda(20, 2, 'cocina', 45), comanda(31, 3, 'entregado', 95)];

Future<ApiFalsa> _atiendoSolo(
  WidgetTester tester, {
  List<String> roles = const ['admin'],
  Size pantalla = const Size(1400, 900),
}) async {
  tester.view.physicalSize = pantalla;
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final api = ApiFalsa(_sala().call);
  final m = await montar(
    tester,
    const MesasPage(),
    api: api,
    usuario: usuarioDePrueba(roles: roles),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text('Atiendo solo'));
  await tester.pumpAndSettle();
  expect(m.plataforma.preferencia('vista_unificada'), '1');
  return api;
}

void main() {
  testWidgets('en pantalla ancha muestra las tres columnas y el pie', (
    tester,
  ) async {
    await _atiendoSolo(tester);

    expect(find.text('1 · Mesas'), findsOneWidget);
    expect(find.text('2 · En cocina'), findsOneWidget);
    expect(find.text('3 · Esperando la cuenta'), findsOneWidget);
    expect(find.text('Para llevar #21'), findsOneWidget);
    expect(find.text('1 pedido entregado'), findsOneWidget);
    // Pedidos en cocina, no mesas: el para llevar cuenta aparte.
    expect(find.text('2 en cocina', findRichText: true), findsOneWidget);
    expect(find.text('S/ 321.50 vendido', findRichText: true), findsOneWidget);
    expect(find.text('Caja abierta'), findsOneWidget);
  });

  testWidgets('el asistente no pide ni ve lo vendido del turno', (
    tester,
  ) async {
    final api = await _atiendoSolo(tester, roles: ['asistente']);

    expect(find.textContaining('vendido', findRichText: true), findsNothing);
    expect(api.llamadas('GET', '/caja/estado'), isEmpty);
  });

  testWidgets('Está listo marca la comanda como entregada', (tester) async {
    final api = await _atiendoSolo(tester);

    await tester.tap(find.text('Está listo').first);
    await tester.pumpAndSettle();

    expect(api.cuerpo('PATCH', '/comandas/20/estado'), {'estado': 'entregado'});
    expect(find.text('Comanda entregada'), findsOneWidget);
  });

  testWidgets('Cobrar en la columna abre la cuenta de esa mesa', (
    tester,
  ) async {
    final api = await _atiendoSolo(tester);

    await tester.tap(find.widgetWithText(FilledButton, 'Cobrar'));
    await tester.pumpAndSettle();

    expect(find.text('Total a cobrar'), findsOneWidget);
    // Abrir la cuenta no cobra nada por sí solo.
    expect(api.llamadas('POST', '/mesas/3/cobrar'), isEmpty);
  });

  testWidgets('tipear un número abre esa mesa; Enter nunca cobra', (
    tester,
  ) async {
    final api = await _atiendoSolo(tester);

    await tester.sendKeyEvent(LogicalKeyboardKey.digit1);
    await tester.sendKeyEvent(LogicalKeyboardKey.digit2);
    await tester.pump(const Duration(milliseconds: 750));
    await tester.pumpAndSettle();
    expect(find.text('Mesa 12 · Nuevo pedido'), findsOneWidget);

    await tester.tap(find.byTooltip('Cerrar'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.digit3);
    await tester.pump(const Duration(milliseconds: 750));
    await tester.pumpAndSettle();
    expect(find.text('Total a cobrar'), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(api.llamadas('POST', '/mesas/3/cobrar'), isEmpty);
  });

  testWidgets('en un celular las columnas pasan a pestañas', (tester) async {
    await _atiendoSolo(tester, pantalla: const Size(400, 800));

    expect(find.byType(TabBar), findsOneWidget);
    expect(find.text('Cocina'), findsOneWidget);

    await tester.tap(find.text('Cocina'));
    await tester.pumpAndSettle();
    expect(find.text('Para llevar #21'), findsOneWidget);
  });
}
