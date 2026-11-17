import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/features/admin/caja/caja_seccion.dart';
import 'package:restomind/features/admin/caja/modelos.dart';
import 'package:restomind/features/admin/caja/reporte_cierre.dart';

import '../../../apoyo.dart';

Map<String, dynamic> _turno({
  int id = 1,
  String estado = 'discrepancia_leve',
  String? nombreTurno,
  double diferencia = -2.5,
  String fecha = '2026-11-17',
}) => {
  'id': id,
  'fecha': fecha,
  'saldo_inicial': 100.0,
  'abierto_en': '2026-11-17T13:00:00',
  'abierto_por': 'admin@test.local',
  'nombre_turno': nombreTurno,
  'ventas_cobradas': 200.0,
  'ventas_yape': 50.0,
  'gastos_efectivo': 20.0,
  'retiros_personales': 0.0,
  'saldo_esperado': 280.0,
  'saldo_contado': 280.0 + diferencia,
  'diferencia': diferencia,
  'variacion_pct': -0.89,
  'razon_discrepancia': 'vuelto mal dado',
  'cerrado_en': '2026-11-17T23:00:00',
  'cerrado_por': 'admin@test.local',
  'estado': estado,
};

Map<String, dynamic> _abierta({bool atrasada = false}) => {
  'hay_caja_abierta': true,
  'caja_abierta': {
    'id': 9,
    'fecha': '2026-11-17',
    'saldo_inicial': 100.0,
    'abierto_en': '2026-11-17T13:00:00',
    'abierto_por': 'admin@test.local',
    'nombre_turno': 'Mañana',
    'estado': 'abierto',
  },
  'es_atrasada': atrasada,
  'ventas_hasta_ahora': 250.0,
  'ventas_efectivo_hasta_ahora': 200.0,
  'ventas_yape_hasta_ahora': 50.0,
  'gastos_hasta_ahora': 20.0,
  'turnos_hoy': 1,
};

const _cerrada = {'hay_caja_abierta': false, 'turnos_hoy': 0};

ApiFalsa _api({
  required Map<String, dynamic> estado,
  List<Object> historial = const [],
}) {
  var actual = estado;
  return ApiFalsa((req) {
    switch ((req.method, req.url.path)) {
      case ('GET', '/api/caja/estado'):
        return (200, actual);
      case ('GET', '/api/caja/historial'):
        return (200, historial);
      case ('GET', '/api/caja/gate'):
        return (200, {'hay_caja_abierta': actual['hay_caja_abierta']});
      case ('POST', '/api/caja/abrir'):
        actual = _abierta();
        return (201, _abierta()['caja_abierta']);
      case ('POST', '/api/caja/cerrar'):
        actual = {..._cerrada, 'turnos_hoy': 1, 'ultimo_cierre_hoy': _turno()};
        return (200, _turno());
    }
    return (404, {'detail': 'no'});
  });
}

Future<void> _pantallaGrande(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

void main() {
  testWidgets('abrir caja manda el saldo y el turno, y refresca el bloqueo '
      'de Mesas y Cocina', (tester) async {
    await _pantallaGrande(tester);
    final api = _api(estado: _cerrada);
    await montar(tester, const CajaSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Saldo inicial (S/)'),
      '150,50',
    );
    await tester.tap(find.text('Tarde'));
    await tester.tap(find.widgetWithText(FilledButton, 'Abrir caja'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/caja/abrir'), {
      'saldo_inicial': 150.5,
      'nombre_turno': 'Tarde',
    });
    expect(api.llamadas('GET', '/caja/gate'), hasLength(1));
    // La pantalla la vuelve a decidir el backend: ahora hay turno abierto.
    expect(find.text('Turno Mañana'), findsOneWidget);
    expect(find.text('Validar y cerrar caja'), findsOneWidget);
  });

  testWidgets('sin saldo válido no abre', (tester) async {
    await _pantallaGrande(tester);
    final api = _api(estado: _cerrada);
    await montar(tester, const CajaSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Abrir caja'));
    await tester.pumpAndSettle();

    expect(api.llamadas('POST', '/caja/abrir'), isEmpty);
    expect(find.text('Escriba un saldo inicial válido'), findsOneWidget);
  });

  testWidgets('turno abierto: muestra lo vendido y avisa si es de otro día', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    await montar(
      tester,
      const CajaSeccion(),
      api: _api(estado: _abierta(atrasada: true)),
    );
    await tester.pumpAndSettle();

    expect(find.text('S/ 250.00'), findsOneWidget);
    expect(find.text('S/ 200.00'), findsOneWidget);
    expect(find.text('Yape/Plin (no entra al conteo)'), findsOneWidget);
    expect(find.text('Turno de un día anterior'), findsOneWidget);
    expect(find.text('Abrir caja'), findsNothing);
  });

  testWidgets('cerrar pide confirmación, manda el conteo e imprime el reporte '
      'con el resultado', (tester) async {
    await _pantallaGrande(tester);
    final api = _api(estado: _abierta());
    final m = await montar(tester, const CajaSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Dinero contado en caja ahora (S/)'),
      '277.5',
    );
    await tester.enterText(
      find.widgetWithText(
        TextFormField,
        'Retiros personales del día (S/, opcional)',
      ),
      '10',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, '¿Por qué no cuadró? (opcional)'),
      '  vuelto mal dado ',
    );
    await tester.tap(find.text('Validar y cerrar caja'));
    await tester.pumpAndSettle();

    expect(find.textContaining('no se puede deshacer'), findsOneWidget);
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(api.llamadas('POST', '/caja/cerrar'), isEmpty);

    await tester.tap(find.text('Validar y cerrar caja'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Cerrar caja'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/caja/cerrar'), {
      'saldo_contado': 277.5,
      'retiros_personales': 10.0,
      'razon_discrepancia': 'vuelto mal dado',
    });
    expect(api.llamadas('GET', '/caja/gate'), hasLength(1));
    final reporte = m.plataforma.impresiones.single;
    expect(reporte, contains('NO CUADRÓ (DIFERENCIA CHICA)'));
    expect(reporte, contains('-S/ 2.50'));
    expect(reporte, contains('Restaurante de Prueba'));
    expect(reporte, isNot(contains('<script')));
    // Después del cierre, el backend dice que ya no hay turno abierto.
    expect(find.text('No cuadró (diferencia chica)'), findsWidgets);
    expect(find.widgetWithText(FilledButton, 'Abrir caja'), findsOneWidget);
  });

  testWidgets('último cierre de hoy: "Turno N de hoy" y se puede reimprimir', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    final m = await montar(
      tester,
      const CajaSeccion(),
      api: _api(
        estado: {..._cerrada, 'turnos_hoy': 2, 'ultimo_cierre_hoy': _turno()},
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Turno 2 de hoy'), findsOneWidget);
    // Abrir otro turno sigue disponible aunque ya hubo cierres hoy.
    expect(find.widgetWithText(FilledButton, 'Abrir caja'), findsOneWidget);

    await tester.tap(find.text('Ver / imprimir reporte'));
    await tester.pumpAndSettle();
    expect(m.plataforma.impresiones.single, contains('NO CUADRÓ'));
  });

  testWidgets('el historial lista cada cierre y lo reimprime', (tester) async {
    await _pantallaGrande(tester);
    final m = await montar(
      tester,
      const CajaSeccion(),
      api: _api(
        estado: _cerrada,
        historial: [
          _turno(
            id: 3,
            estado: 'cuadrado',
            diferencia: 0,
            nombreTurno: 'Noche',
          ),
          _turno(id: 2, estado: 'cerrado_automatico', diferencia: 0),
          _turno(id: 1, estado: 'discrepancia_grave', diferencia: -40),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('17/11/2026 · '), findsNWidgets(3));
    expect(find.textContaining(' · Noche'), findsOneWidget);
    expect(find.text('Caja cuadrada · +S/ 0.00'), findsOneWidget);
    expect(
      find.text('Se cerró sola (falta contar el dinero) · +S/ 0.00'),
      findsOneWidget,
    );
    expect(
      find.text('No cuadró (diferencia grande) · -S/ 40.00'),
      findsOneWidget,
    );

    await tester.tap(find.byTooltip('Ver / imprimir reporte').last);
    await tester.pumpAndSettle();
    expect(
      m.plataforma.impresiones.single,
      contains('NO CUADRÓ (DIFERENCIA GRANDE)'),
    );
  });

  test('el reporte pone el resultado primero y no depende de la red', () {
    final html = reporteCierreHtml(
      Turno.desdeJson(_turno(estado: 'cuadrado', diferencia: 0)),
      negocio: 'La <Marisquería>',
      impreso: DateTime(2026, 11, 17, 23, 5),
    );
    expect(html.indexOf('CAJA CUADRADA'), lessThan(html.indexOf('Esperado')));
    expect(html, contains('La &lt;Marisquería&gt;'));
    expect(html, contains('martes, 17 de noviembre de 2026'));
    expect(html, contains('vuelto mal dado'));
    expect(html, isNot(contains('http')));
    expect(html, isNot(contains('<script')));
  });
}
