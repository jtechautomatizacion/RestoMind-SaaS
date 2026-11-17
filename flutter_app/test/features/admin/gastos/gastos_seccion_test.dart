import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/core/formato.dart';
import 'package:restomind/features/admin/gastos/gastos_seccion.dart';
import 'package:restomind/features/admin/gastos/modelos.dart';

import '../../../apoyo.dart';

final _hoy = fechaIso(DateTime.now());

const _insumo = {
  'id': 3,
  'cliente_id': 'test-cliente-001',
  'nombre': 'Pescado',
  'unidad': 'kg',
  'cantidad_actual': 4.0,
  'cantidad_minima': 8.0,
  'estado': 'bajo',
  'creado_en': '2026-11-17T10:00:00',
};

Map<String, dynamic> _movimiento({required bool revertido}) => {
  'id': 11,
  'insumo_id': 3,
  'tipo': 'entrada',
  'cantidad': 5.0,
  'razon': 'compra',
  'saldo_despues': 9.0,
  'fecha': '${_hoy}T00:00:00',
  'usuario_nombre': 'Admin de prueba',
  'creado_en': '${_hoy}T15:00:00',
  'revertido': revertido,
};

/// API de Gastos: un gasto de hoy y un insumo con un movimiento. Deshacer
/// marca el movimiento como revertido, como hace el backend.
ApiFalsa _api() {
  var revertido = false;
  return ApiFalsa((req) {
    final ruta = '${req.method} ${req.url.path}';
    switch (ruta) {
      case 'GET /api/compras':
        return (
          200,
          [
            {
              'id': 1,
              'cliente_id': 'test-cliente-001',
              'descripcion': 'Limones',
              'categoria': 'Insumos',
              'monto': 12.5,
              'fecha': _hoy,
              'estado': 'registrado',
              'creado_en': '${_hoy}T12:00:00',
            },
          ],
        );
      case 'GET /api/insumos':
        return (200, [_insumo]);
      case 'POST /api/compras':
        return (201, {'id': 2});
      case 'POST /api/insumos/3/movimientos':
        return (201, _movimiento(revertido: false));
      case 'GET /api/insumos/3/movimientos':
        return (200, [_movimiento(revertido: revertido)]);
      case 'DELETE /api/insumos/3/movimientos/11':
        revertido = true;
        return (
          200,
          {
            ..._movimiento(revertido: false),
            'id': 12,
            'tipo': 'salida',
            'razon': 'reversion',
            'saldo_despues': 4.0,
          },
        );
    }
    return (404, {'detail': 'no esperado: $ruta'});
  });
}

Future<void> _tocar(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.tap(f);
  await tester.pumpAndSettle();
}

/// El botón principal de una hoja, sea FilledButton o FilledButton.icon.
Finder _botonPrincipal(String texto) => find.ancestor(
  of: find.text(texto).last,
  matching: find.byWidgetPredicate((w) => w is FilledButton),
);

Future<void> _abrirInventario(WidgetTester tester) =>
    _tocar(tester, find.text('Inventario'));

void main() {
  testWidgets('registrar un gasto manda descripción, categoría, monto y hoy', (
    tester,
  ) async {
    final api = _api();
    await montar(tester, const GastosSeccion(), api: api);
    await tester.pumpAndSettle();
    expect(find.text('Limones'), findsOneWidget);

    await _tocar(tester, find.text('Registrar gasto'));
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Descripción'),
      'Pescado del mercado',
    );
    await _tocar(tester, find.byType(DropdownButtonFormField<String?>));
    await _tocar(tester, find.text('Insumos').last);

    await tester.enterText(find.widgetWithText(TextFormField, 'Monto'), '0');
    await _tocar(tester, _botonPrincipal('Guardar'));
    expect(api.llamadas('POST', '/compras'), isEmpty);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Monto'),
      '85.50',
    );
    await _tocar(tester, _botonPrincipal('Guardar'));

    expect(api.cuerpo('POST', '/compras'), {
      'descripcion': 'Pescado del mercado',
      'categoria': 'Insumos',
      'fecha': _hoy,
      'monto': 85.5,
    });
  });

  group('fecha de un gasto', () {
    final hoy = DateTime(2026, 11, 17, 21, 30);

    test('mañana se rechaza', () {
      expect(
        errorFechaGasto(DateTime(2026, 11, 18), hoy: hoy),
        'La fecha no puede ser futura',
      );
    });

    test('hoy (a cualquier hora) y ayer se aceptan', () {
      expect(errorFechaGasto(DateTime(2026, 11, 17, 23, 59), hoy: hoy), isNull);
      expect(errorFechaGasto(DateTime(2026, 11, 16), hoy: hoy), isNull);
    });
  });

  testWidgets('una entrada de stock manda tipo, cantidad, motivo y fecha', (
    tester,
  ) async {
    final api = _api();
    await montar(tester, const GastosSeccion(), api: api);
    await tester.pumpAndSettle();

    // Cerrado muestra solo el resumen; abierto, la fila del insumo.
    expect(find.text('1 bajo'), findsOneWidget);
    await _abrirInventario(tester);
    await _tocar(tester, find.byTooltip('Registrar entrada'));

    await tester.enterText(find.widgetWithText(TextFormField, 'Cantidad'), '5');
    await _tocar(tester, _botonPrincipal('Registrar entrada'));

    expect(api.cuerpo('POST', '/insumos/3/movimientos'), {
      'tipo': 'entrada',
      'cantidad': 5,
      'razon': 'compra',
      'fecha': _hoy,
    });
    expect(find.text('+5 kg · quedan 9 kg'), findsOneWidget);
  });

  testWidgets('deshacer pide confirmación, se apaga mientras tanto y '
      'manda UNA sola reversión', (tester) async {
    final api = _api();
    await montar(tester, const GastosSeccion(), api: api);
    await tester.pumpAndSettle();
    await _abrirInventario(tester);
    await _tocar(tester, find.byTooltip('Ver movimientos'));
    expect(
      find.text(
        'Llegó mercadería · ${fecha(DateTime.now())} · '
        'Admin de prueba',
      ),
      findsOneWidget,
    );

    final deshacer = find.byTooltip('Deshacer este movimiento');

    // Cancelar no manda nada.
    await _tocar(tester, deshacer);
    expect(find.text('Deshacer movimiento'), findsOneWidget);
    await _tocar(tester, find.text('Cancelar'));
    expect(api.llamadas('DELETE', '/insumos/3/movimientos/11'), isEmpty);

    // Con la confirmación abierta, el botón ya no responde a otro toque.
    await _tocar(tester, deshacer);
    final boton = tester.widget<IconButton>(
      find.widgetWithIcon(IconButton, Icons.undo),
    );
    expect(boton.onPressed, isNull);

    await _tocar(tester, find.widgetWithText(FilledButton, 'Deshacer'));
    expect(api.llamadas('DELETE', '/insumos/3/movimientos/11'), hasLength(1));
    // Ya revertido: no se ofrece deshacerlo otra vez, y el stock se corrigió.
    expect(deshacer, findsNothing);
    expect(find.text('4 kg en stock'), findsOneWidget);
  });

  test('las cantidades de stock no muestran decimales de más', () {
    expect(cantidad(20), '20');
    expect(cantidad(0.5), '0.5');
    expect(cantidad(2.25), '2.25');
  });
}
