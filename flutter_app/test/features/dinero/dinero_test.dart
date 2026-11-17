import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/design/widgets.dart';
import 'package:restomind/features/dinero/dinero_page.dart';
import 'package:restomind/features/dinero/formato_dinero.dart';
import 'package:restomind/features/dinero/modelos.dart';
import 'package:restomind/features/dinero/tabla_diaria.dart';

import '../../apoyo.dart';

Map<String, dynamic> _resumen() => {
  'periodo_dias': 7,
  'serie': [
    // Lunes: perdió plata. Martes (hoy): ganó.
    {
      'fecha': '2026-11-16',
      'ventas': 80.0,
      'gastos': 122.5,
      'ganancia': -42.5,
      'comandas': 3,
    },
    {
      'fecha': '2026-11-17',
      'ventas': 1204.5,
      'gastos': 0.0,
      'ganancia': 1204.5,
      'comandas': 21,
    },
  ],
  'totales': {
    'ventas': 1284.5,
    'gastos': 122.5,
    'ganancia': 1162.0,
    'comandas': 24,
  },
  'top_platos': [
    {'nombre': 'Ceviche clásico', 'cantidad': 12, 'ingresos': 540.0},
    {'nombre': 'Chicha morada', 'cantidad': 30, 'ingresos': 150.0},
  ],
  'top_gastos': [
    {'categoria': 'Insumos', 'cantidad': 1, 'monto': 122.5},
  ],
  'por_tipo_pedido': [
    {'tipo': 'mesa', 'pedidos': 18, 'total': 1027.6},
    {'tipo': 'llevar', 'pedidos': 6, 'total': 256.9},
  ],
  'por_metodo_pago': [
    {'tipo': 'efectivo', 'pedidos': 24, 'total': 1284.5},
    {'tipo': 'yape', 'pedidos': 0, 'total': 0.0},
  ],
};

ApiFalsa _api() => ApiFalsa(
  (req) => req.url.path == '/api/dashboard/resumen'
      ? (200, _resumen())
      : (200, {'archivo': 'xlsx'}),
);

Future<void> _anchoDePantalla(WidgetTester tester, double ancho) async {
  tester.view
    ..physicalSize = Size(ancho, 2400)
    ..devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

Finder _enIndicador(String texto) =>
    find.descendant(of: find.byType(Indicador), matching: find.text(texto));

Finder _enTabla(String texto) =>
    find.descendant(of: find.byType(TablaDiaria), matching: find.text(texto));

void main() {
  testWidgets('muestra los totales del período con sus céntimos exactos', (
    tester,
  ) async {
    await _anchoDePantalla(tester, 900);
    final api = _api();
    await montar(tester, const DineroPage(), api: api);
    await tester.pumpAndSettle();

    expect(
      api.llamadas('GET', '/dashboard/resumen').single.url.query,
      'dias=7',
    );
    expect(_enIndicador('S/ 1,284.50'), findsOneWidget);
    expect(_enIndicador('S/ 122.50'), findsOneWidget);
    expect(_enIndicador('S/ 1,162.00'), findsOneWidget);
    expect(_enIndicador('90%'), findsOneWidget);
    expect(find.text('Últimos 7 días'), findsOneWidget);

    // Las listas de abajo, con el mismo dato sin redondear.
    expect(find.text('Ceviche clásico'), findsOneWidget);
    expect(find.text('S/ 540.00'), findsOneWidget);
    expect(find.text('1 gasto'), findsOneWidget);
    expect(find.text('18 pedidos · 80%'), findsOneWidget);
    expect(find.text('Yape/Plin'), findsOneWidget);
  });

  testWidgets('la tabla va de lo más reciente a lo más antiguo y marca el día '
      'en pérdida', (tester) async {
    await _anchoDePantalla(tester, 900);
    await montar(tester, const DineroPage(), api: _api());
    await tester.pumpAndSettle();

    final hoy = tester.getTopLeft(_enTabla('Mar 17 nov')).dy;
    final ayer = tester.getTopLeft(_enTabla('Lun 16 nov')).dy;
    expect(hoy, lessThan(ayer));
    expect(_enTabla('S/ -42.50'), findsOneWidget);
    expect(_enTabla('-53%'), findsOneWidget);
    expect(_enTabla('100%'), findsOneWidget);
  });

  testWidgets('en un celular la tabla oculta Gastos y Margen', (tester) async {
    await _anchoDePantalla(tester, 400);
    await montar(tester, const DineroPage(), api: _api());
    await tester.pumpAndSettle();

    expect(_enTabla('Ventas'), findsOneWidget);
    expect(_enTabla('Ganancia'), findsOneWidget);
    expect(_enTabla('Gastos'), findsNothing);
    expect(_enTabla('Margen'), findsNothing);
    expect(_enTabla('S/ 122.50'), findsNothing);
  });

  testWidgets('a lo ancho la tabla muestra las cinco columnas', (tester) async {
    await _anchoDePantalla(tester, 481);
    await montar(tester, const DineroPage(), api: _api());
    await tester.pumpAndSettle();

    expect(_enTabla('Gastos'), findsOneWidget);
    expect(_enTabla('Margen'), findsOneWidget);
  });

  testWidgets('un atajo de días vuelve a pedir el resumen de ese período', (
    tester,
  ) async {
    await _anchoDePantalla(tester, 900);
    final api = _api();
    await montar(tester, const DineroPage(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('30 días'));
    await tester.pumpAndSettle();

    expect(api.llamadas('GET', '/dashboard/resumen').last.url.query, 'dias=30');
    expect(find.text('Últimos 30 días'), findsOneWidget);
  });

  testWidgets('el Excel se pide con el mismo período y se entrega como '
      'descarga', (tester) async {
    await _anchoDePantalla(tester, 900);
    final api = _api();
    final montado = await montar(tester, const DineroPage(), api: api);
    await tester.pumpAndSettle();

    final boton = find.text('Descargar reporte Excel');
    await tester.ensureVisible(boton);
    await tester.tap(boton);
    await tester.pumpAndSettle();

    expect(
      api.llamadas('GET', '/dashboard/reporte-excel').single.url.query,
      'dias=7',
    );
    expect(montado.plataforma.descargas, ['reporte.xlsx']);
    expect(find.text('Reporte descargado'), findsOneWidget);
  });

  group('reglas del período y del gráfico', () {
    test('las etiquetas de barra no inventan redondeos', () {
      expect(compacto(122.5), '122.50');
      expect(compacto(150), '150');
      expect(compacto(999.99), '999.99');
      expect(compacto(1500), '1.5k');
      expect(compacto(2000), '2k');
    });

    test('el rango se valida como lo valida el backend', () {
      expect(
        validarRango(DateTime(2026, 11, 17), DateTime(2026, 11, 1)),
        'La fecha inicial no puede ser mayor a la final',
      );
      // Un año completo con hoy incluido son 366 días: todavía entra.
      expect(
        validarRango(DateTime(2025, 11, 17), DateTime(2026, 11, 17)),
        isNull,
      );
      expect(
        validarRango(DateTime(2025, 11, 16), DateTime(2026, 11, 17)),
        'El rango no puede superar 366 días (eligió 367)',
      );
    });

    test('"últimos 7 días" son hoy y los 6 anteriores', () {
      final (desde, hasta) = const Periodo.ultimos(
        7,
      ).fechas(DateTime(2026, 11, 17, 20, 30));
      expect(desde, DateTime(2026, 11, 11));
      expect(hasta, DateTime(2026, 11, 17));
      expect(Periodo.rango(desde, hasta).query, {
        'desde': '2026-11-11',
        'hasta': '2026-11-17',
      });
    });
  });
}
