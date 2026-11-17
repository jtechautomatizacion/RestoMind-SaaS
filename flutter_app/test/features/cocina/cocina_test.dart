import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/design/papel.dart';
import 'package:restomind/features/cocina/cocina_page.dart';

import '../../apoyo.dart';

Map<String, dynamic> _comanda(
  int id, {
  required int mesa,
  required String creadoEn,
  required int minutos,
  List<(int, String)> platos = const [(1, 'Ceviche')],
}) => {
  'id': id,
  'numero_mesa': mesa,
  'estado': mesa == 0 ? 'cobrado' : 'cocina',
  'creado_en': creadoEn,
  'minutos_transcurridos': minutos,
  'platos': [
    for (final (cantidad, nombre) in platos)
      {'nombre': nombre, 'cantidad': cantidad},
  ],
};

/// La pantalla deja un Timer de refresco: hay que desmontarla para que la
/// prueba no termine con un temporizador pendiente.
Future<void> desmontar(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
}

CronometroComanda cronometroDe(WidgetTester tester, String texto) =>
    tester.widget<CronometroComanda>(
      find.ancestor(
        of: find.text(texto),
        matching: find.byType(CronometroComanda),
      ),
    );

void main() {
  testWidgets('el pedido más antiguo va primero y desde 15 min se marca en '
      'rojo', (tester) async {
    // Una sola columna, para comparar el orden de arriba hacia abajo.
    tester.view
      ..physicalSize = const Size(420, 1400)
      ..devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    // Llegan desordenados a propósito: el orden no puede depender de que el
    // backend los mande ya ordenados.
    final api = ApiFalsa(
      (req) => (
        200,
        [
          _comanda(
            2,
            mesa: 7,
            creadoEn: '2026-11-17T15:10:00',
            minutos: 14,
            platos: [(2, 'Lomo saltado')],
          ),
          _comanda(1, mesa: 4, creadoEn: '2026-11-17T14:50:00', minutos: 15),
          _comanda(3, mesa: 0, creadoEn: '2026-11-17T15:20:00', minutos: 3),
        ],
      ),
    );
    await montar(tester, const CocinaPage(), api: api);
    await tester.pumpAndSettle();

    // Orden de lectura: en el riel de izquierda a derecha, en el celular de
    // arriba abajo. El más antiguo, primero.
    double orden(String t) {
      final o = tester.getTopLeft(find.text(t));
      return o.dy * 10000 + o.dx;
    }

    expect(orden('Mesa 4'), lessThan(orden('Mesa 7')));
    expect(orden('Mesa 7'), lessThan(orden('Para llevar #3')));

    expect(cronometroDe(tester, '15 min').atrasada, isTrue);
    expect(cronometroDe(tester, '14 min').atrasada, isFalse);
    expect(cronometroDe(tester, '3 min').atrasada, isFalse);
    expect(find.text('2x Lomo saltado'), findsOneWidget);

    await desmontar(tester);
  });

  testWidgets('"Listo" manda el pedido como entregado y la tarjeta no vuelve '
      'aunque una consulta vieja la traiga', (tester) async {
    final api = ApiFalsa(
      (req) => req.method == 'PATCH'
          ? (200, {'id': 1, 'estado': 'entregado'})
          // Siempre la trae: simula la respuesta de una consulta que salió
          // antes de tocar Listo.
          : (
              200,
              [
                _comanda(
                  1,
                  mesa: 4,
                  creadoEn: '2026-11-17T14:50:00',
                  minutos: 5,
                ),
                _comanda(
                  2,
                  mesa: 6,
                  creadoEn: '2026-11-17T14:55:00',
                  minutos: 2,
                ),
              ],
            ),
    );
    await montar(tester, const CocinaPage(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Listo').first);
    await tester.pumpAndSettle();

    expect(api.llamadas('PATCH', '/comandas/1/estado'), hasLength(1));
    expect(api.cuerpo('PATCH', '/comandas/1/estado'), {'estado': 'entregado'});
    expect(find.text('Mesa 4'), findsNothing);
    expect(find.text('Comanda entregada'), findsOneWidget);

    await tester.pump(CocinaPage.intervalo);
    await tester.pumpAndSettle();
    expect(find.text('Mesa 4'), findsNothing);
    expect(find.text('Mesa 6'), findsOneWidget);

    await desmontar(tester);
  });

  testWidgets('se actualiza sola cada pocos segundos y deja de consultar al '
      'salir', (tester) async {
    var vuelta = 0;
    final api = ApiFalsa((req) {
      vuelta++;
      return (
        200,
        [
          if (vuelta > 1)
            _comanda(9, mesa: 2, creadoEn: '2026-11-17T15:00:00', minutos: 0),
        ],
      );
    });
    await montar(tester, const CocinaPage(), api: api);
    await tester.pumpAndSettle();
    expect(find.text('Sin comandas pendientes'), findsOneWidget);

    await tester.pump(CocinaPage.intervalo);
    await tester.pumpAndSettle();
    expect(find.text('Mesa 2'), findsOneWidget);

    await desmontar(tester);
    final consultas = api.llamadas('GET', '/monitor/cocina').length;
    await tester.pump(CocinaPage.intervalo * 3);
    expect(api.llamadas('GET', '/monitor/cocina'), hasLength(consultas));
  });

  testWidgets('una falla pasajera no borra los pedidos de la pantalla', (
    tester,
  ) async {
    var caida = false;
    final api = ApiFalsa(
      (req) => caida
          ? (500, {'detail': 'error'})
          : (
              200,
              [
                _comanda(
                  1,
                  mesa: 4,
                  creadoEn: '2026-11-17T14:50:00',
                  minutos: 5,
                ),
              ],
            ),
    );
    await montar(tester, const CocinaPage(), api: api);
    await tester.pumpAndSettle();

    caida = true;
    await tester.pump(CocinaPage.intervalo);
    await tester.pumpAndSettle();
    expect(find.text('Mesa 4'), findsOneWidget);
    expect(find.text('Sin conexión'), findsOneWidget);

    await desmontar(tester);
  });

  testWidgets('Reimprimir encola el ticket de cocina', (tester) async {
    final api = ApiFalsa(
      (req) => req.method == 'POST'
          ? (201, {'id': 1})
          : (
              200,
              [
                _comanda(
                  5,
                  mesa: 3,
                  creadoEn: '2026-11-17T14:50:00',
                  minutos: 5,
                ),
              ],
            ),
    );
    await montar(tester, const CocinaPage(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Reimprimir'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/impresion/reimprimir'), {
      'comanda_id': 5,
      'tipo_documento': 'cocina',
    });
    expect(find.text('Pedido a la impresora'), findsOneWidget);

    await desmontar(tester);
  });
}
