import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/features/admin/carta/carta_seccion.dart';
import 'package:restomind/features/admin/carta/modelos.dart';

import '../../../apoyo.dart';
import 'plataforma_con_foto.dart';

Map<String, dynamic> _plato(int id, String nombre, String categoria) => {
  'id': id,
  'cliente_id': 'test-cliente-001',
  'nombre': nombre,
  'categoria': categoria,
  'precio_venta': 20.0,
  'descripcion': null,
  'imagen_url': null,
  'estado': 'activo',
  'creado_en': '2026-11-17T10:00:00',
};

const _categorias = [
  {'id': 1, 'cliente_id': 'c', 'nombre': 'Bebidas', 'icono': '🥤'},
  {'id': 2, 'cliente_id': 'c', 'nombre': 'Cebiches', 'icono': '🐟'},
];

/// API de la carta: dos platos de categorías distintas. Crear devuelve el
/// plato 9, y subir su foto devuelve el mismo plato.
ApiFalsa _api() => ApiFalsa((req) {
  final ruta = '${req.method} ${req.url.path}';
  return switch (ruta) {
    'GET /api/platos' => (
      200,
      [
        _plato(7, 'Ceviche clásico', 'Cebiches'),
        _plato(8, 'Chicha morada', 'Bebidas'),
      ],
    ),
    'GET /api/categorias' => (200, _categorias),
    'POST /api/platos' => (201, _plato(9, 'Leche de tigre', 'Cebiches')),
    'POST /api/platos/9/imagen' => (
      200,
      _plato(9, 'Leche de tigre', 'Cebiches'),
    ),
    _ => (404, {'detail': 'no esperado: $ruta'}),
  };
});

Future<void> _llenarPlato(WidgetTester tester, {required String precio}) async {
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Nombre'),
    'Leche de tigre',
  );
  await tester.tap(find.byType(DropdownButtonFormField<String>));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Cebiches').last);
  await tester.pumpAndSettle();
  await tester.enterText(
    find.widgetWithText(TextFormField, 'Precio de venta'),
    precio,
  );
}

Future<void> _guardar(WidgetTester tester) async {
  final boton = find.widgetWithText(FilledButton, 'Guardar');
  await tester.ensureVisible(boton);
  await tester.tap(boton);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('los chips filtran la carta por categoría', (tester) async {
    final api = _api();
    await montar(tester, const CartaSeccion(), api: api);
    await tester.pumpAndSettle();

    expect(find.text('Ceviche clásico'), findsOneWidget);
    expect(find.text('Chicha morada'), findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Bebidas'));
    await tester.pumpAndSettle();
    expect(find.text('Ceviche clásico'), findsNothing);
    expect(find.text('Chicha morada'), findsOneWidget);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Todas'));
    await tester.pumpAndSettle();
    expect(find.text('Ceviche clásico'), findsOneWidget);
  });

  testWidgets(
    'crear un plato exige precio mayor a 0 y manda el cuerpo exacto',
    (tester) async {
      final api = _api();
      await montar(tester, const CartaSeccion(), api: api);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Nuevo plato'));
      await tester.pumpAndSettle();
      await _llenarPlato(tester, precio: '0');
      await _guardar(tester);

      expect(api.llamadas('POST', '/platos'), isEmpty);
      expect(
        find.text('Escriba un precio mayor a 0, con hasta dos decimales'),
        findsOneWidget,
      );

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Precio de venta'),
        '45,5',
      );
      await _guardar(tester);

      expect(api.cuerpo('POST', '/platos'), {
        'nombre': 'Leche de tigre',
        'categoria': 'Cebiches',
        'precio_venta': 45.5,
        'descripcion': null,
      });
      // Sin foto elegida no se sube nada.
      expect(api.llamadas('POST', '/platos/9/imagen'), isEmpty);
    },
  );

  testWidgets('la foto se sube después de crear, al id que dio el servidor', (
    tester,
  ) async {
    final api = _api();
    await montarConFoto(tester, const CartaSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nuevo plato'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Elegir foto'));
    await tester.pumpAndSettle();
    expect(find.text('Cambiar foto'), findsOneWidget);
    await _llenarPlato(tester, precio: '18');
    await _guardar(tester);

    final subidas = api.llamadas('POST', '/platos/9/imagen');
    expect(subidas, hasLength(1));
    expect(subidas.single.headers['content-type'], contains('multipart/'));
    final cuerpo = latin1.decode(subidas.single.bodyBytes);
    expect(cuerpo, contains('name="archivo"'));
    expect(cuerpo, contains('filename="foto.png"'));
  });

  group('precio', () {
    test('acepta coma o punto y hasta dos decimales', () {
      expect(leerPrecio('12,50'), 12.5);
      expect(leerPrecio('7'), 7);
      expect(leerPrecio('1.999'), isNull);
      expect(leerPrecio('0.00'), isNull);
      expect(leerPrecio('-3'), isNull);
    });
  });
}
