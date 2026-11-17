import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/features/mesas/mesas_page.dart';

import '../../apoyo.dart';
import 'backend_falso.dart';

/// Una sala con las tres situaciones: la 1 libre, la 2 esperando la comida y
/// la 3 servida esperando la cuenta.
BackendSala _salaTipica({double cuentaMesa3 = 95}) => BackendSala()
  ..mesas = [
    mesa(1, 1),
    mesa(2, 2, ocupada: true, cuenta: 45),
    mesa(3, 3, ocupada: true, cuenta: cuentaMesa3),
  ]
  ..cocina = [enCocina(20, 2)]
  ..comandas = [
    comanda(20, 2, 'cocina', 45),
    comanda(31, 3, 'entregado', cuentaMesa3),
  ];

Finder _enDialogo(String texto) =>
    find.descendant(of: find.byType(AlertDialog), matching: find.text(texto));

Future<void> _abrirCuentaMesa3(WidgetTester tester) async {
  await tester.tap(find.bySemanticsLabel(RegExp(r'^Mesa 3,')));
  await tester.pumpAndSettle();
  expect(find.text('Total a cobrar'), findsOneWidget);
}

Future<void> _cobrarYConfirmar(WidgetTester tester, String boton) async {
  await tester.tap(find.widgetWithText(FilledButton, boton).first);
  await tester.pumpAndSettle();
  await tester.tap(_enDialogo('Cobrar'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('la grilla muestra libre, en cocina y por cobrar', (
    tester,
  ) async {
    final api = ApiFalsa(_salaTipica().call);
    await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();

    expect(find.text('Libre'), findsOneWidget);
    expect(find.text('En cocina'), findsOneWidget);
    expect(find.text('Por cobrar'), findsOneWidget);
    expect(find.text('Para llevar'), findsOneWidget);
    expect(find.text('S/ 95.00'), findsOneWidget);
  });

  testWidgets('quien solo cobra no puede abrir un pedido nuevo', (
    tester,
  ) async {
    final api = ApiFalsa(_salaTipica().call);
    await montar(
      tester,
      const MesasPage(),
      api: api,
      usuario: usuarioDePrueba(roles: ['cajero']),
    );
    await tester.pumpAndSettle();

    expect(find.text('Para llevar'), findsNothing);
    await tester.tap(find.bySemanticsLabel(RegExp(r'^Mesa 1 libre')));
    await tester.pumpAndSettle();
    expect(find.textContaining('Nuevo pedido'), findsNothing);
    // Sí cobra: la cuenta se abre, pero sin "Agregar pedido".
    await _abrirCuentaMesa3(tester);
    expect(find.text('Agregar pedido'), findsNothing);
    expect(api.llamadas('GET', '/platos'), isEmpty);
  });

  testWidgets('el pedido de una mesa manda platos y cantidades', (
    tester,
  ) async {
    final api = ApiFalsa(_salaTipica().call);
    await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel(RegExp(r'^Mesa 1 libre')));
    await tester.pumpAndSettle();
    expect(find.text('Mesa 1 · Nuevo pedido'), findsOneWidget);

    await tester.tap(find.text('Ceviche'));
    await tester.tap(find.text('Ceviche'));
    await tester.tap(find.text('Fondos'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Lomo saltado'));
    await tester.pumpAndSettle();
    expect(find.text('S/ 128.00'), findsOneWidget);

    await tester.tap(find.text('Enviar a cocina'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/comandas'), {
      'numero_mesa': 1,
      'tipo_pedido': 'mesa',
      'platos': [
        {'plato_id': 101, 'cantidad': 2},
        {'plato_id': 102, 'cantidad': 1},
      ],
    });
    expect(find.text('Comanda enviada a cocina'), findsOneWidget);
  });

  testWidgets('para llevar se cobra con el método elegido', (tester) async {
    final api = ApiFalsa(_salaTipica().call);
    final m = await montar(
      tester,
      const MesasPage(),
      api: api,
      usuario: usuarioDePrueba(usarSunat: false),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Para llevar'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ceviche'));
    await tester.tap(find.text('Yape/Plin'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cobrar y enviar a cocina'));
    await tester.pumpAndSettle();
    await tester.tap(_enDialogo('Cobrar'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/comandas'), {
      'numero_mesa': 0,
      'tipo_pedido': 'llevar',
      'platos': [
        {'plato_id': 101, 'cantidad': 1},
      ],
      'metodo_pago': 'yape',
    });
    expect(
      find.text('Cobrado en Yape/Plin y enviado a cocina'),
      findsOneWidget,
    );

    // El papel del comensal sale a pedido, desde el aviso, y como ya está
    // pagado no manda a pagarlo de nuevo en caja.
    await tester.tap(find.text('Imprimir'));
    await tester.pump();
    final html = m.plataforma.impresiones.single;
    expect(html, contains('TOTAL PAGADO'));
    expect(html, isNot(contains('ENTREGUE ESTA HOJA EN CAJA')));
  });

  testWidgets('cobrar con DNI cobra y emite el comprobante a ese documento', (
    tester,
  ) async {
    final backend = _salaTipica()
      ..documento = (
        200,
        {
          'documento': '73081441',
          'tipo': 'DNI',
          'encontrado': true,
          'nombre': 'JUAN PEREZ',
        },
      );
    final api = ApiFalsa(backend.call);
    final m = await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();
    await _abrirCuentaMesa3(tester);

    await tester.tap(find.text('Yape/Plin'));
    await tester.tap(find.text('Con DNI'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '73081441');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.text('JUAN PEREZ'), findsOneWidget);

    await _cobrarYConfirmar(tester, 'Cobrar');

    expect(api.cuerpo('POST', '/mesas/3/cobrar'), {'metodo_pago': 'yape'});
    expect(api.cuerpo('POST', '/facturas/generar'), {
      'comanda_ids': [31],
      'documento_comprador': '73081441',
      'razon_social_manual': 'JUAN PEREZ',
    });
    expect(m.plataforma.impresiones.single, contains('B001-00000007'));
  });

  testWidgets('desde S/ 700 sin documento no se puede cobrar', (tester) async {
    final api = ApiFalsa(_salaTipica(cuentaMesa3: 750).call);
    await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();
    await _abrirCuentaMesa3(tester);

    expect(find.textContaining('Desde S/ 700 SUNAT exige'), findsOneWidget);
    final boton = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Cobrar'),
    );
    expect(boton.onPressed, isNull);
    expect(api.llamadas('POST', '/mesas/3/cobrar'), isEmpty);
  });

  testWidgets('el RUC dice qué comprobante va a salir según el régimen', (
    tester,
  ) async {
    final backend = _salaTipica()
      ..documento = (
        200,
        {
          'documento': '20000000001',
          'tipo': 'RUC',
          'encontrado': true,
          'nombre': 'EMPRESA SAC',
        },
      );
    final api = ApiFalsa(backend.call);
    await montar(
      tester,
      const MesasPage(),
      api: api,
      usuario: usuarioDePrueba(emiteFacturas: true),
    );
    await tester.pumpAndSettle();
    await _abrirCuentaMesa3(tester);
    await tester.tap(find.text('Con RUC'));
    await tester.pumpAndSettle();

    // Un dígito verificador malo se atrapa sin consultar.
    await tester.enterText(find.byType(TextField), '20000000002');
    await tester.pump();
    expect(find.textContaining('no parece un RUC válido'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '20000000001');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
    expect(find.text('Factura · F001'), findsOneWidget);
    expect(api.llamadas('GET', '/documento/20000000001'), hasLength(1));
    expect(api.llamadas('GET', '/documento/20000000002'), isEmpty);
  });

  testWidgets('con la facturación apagada en el servidor no se muestra error', (
    tester,
  ) async {
    final backend = _salaTipica()
      ..factura = (
        409,
        {
          'detail': {
            'codigo': 'FACTURACION_DESACTIVADA',
            'mensaje': 'Este restaurante tiene la facturación desactivada.',
          },
        },
      )
      ..identidad = {
        'email': 'admin@test.local',
        'nombre': 'Admin',
        'rol': 'admin',
        'roles': ['admin'],
        'cliente_id': 'test-cliente-001',
        'cliente_nombre': 'Restaurante de Prueba',
        'cliente_usar_sunat': false,
      };
    final api = ApiFalsa(backend.call);
    final m = await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();
    await _abrirCuentaMesa3(tester);

    await _cobrarYConfirmar(tester, 'Cobrar');

    expect(api.llamadas('POST', '/facturas/generar'), hasLength(1));
    expect(api.llamadas('GET', '/auth/me'), hasLength(1));
    expect(m.servicios.sesion.usuario!.usarSunat, isFalse);
    expect(
      find.text(
        'Venta registrada en caja. Este restaurante no emite comprobantes.',
      ),
      findsOneWidget,
    );
    expect(find.textContaining('NO se emitió'), findsNothing);
    expect(m.plataforma.impresiones, isEmpty);
  });

  testWidgets('si SUNAT no responde se imprime el ticket de contingencia', (
    tester,
  ) async {
    final backend = _salaTipica()
      ..factura = (
        502,
        {
          'detail': {
            'mensaje': 'La boleta se guardó pero no se pudo generar todavía',
            'factura': facturaJson(estado: 'pendiente'),
          },
        },
      );
    final api = ApiFalsa(backend.call);
    final m = await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();
    await _abrirCuentaMesa3(tester);

    await _cobrarYConfirmar(tester, 'Cobrar');

    expect(
      m.plataforma.impresiones.single,
      contains('Comprobante en proceso de transmisión a SUNAT'),
    );
    expect(find.textContaining('Ticket impreso'), findsOneWidget);
  });

  testWidgets('sin facturación no se piden DNI ni RUC ni se emite nada', (
    tester,
  ) async {
    final api = ApiFalsa(_salaTipica().call);
    await montar(
      tester,
      const MesasPage(),
      api: api,
      usuario: usuarioDePrueba(usarSunat: false),
    );
    await tester.pumpAndSettle();
    await _abrirCuentaMesa3(tester);

    expect(find.text('Sin documento'), findsNothing);
    expect(find.text('Con RUC'), findsNothing);
    expect(find.text('Con DNI'), findsNothing);

    await _cobrarYConfirmar(tester, 'Cobrar');

    expect(api.cuerpo('POST', '/mesas/3/cobrar'), {'metodo_pago': 'efectivo'});
    expect(api.llamadas('POST', '/facturas/generar'), isEmpty);
    expect(find.textContaining('Cobrado S/ 95.00 en Efectivo'), findsOneWidget);
  });

  testWidgets('con algo todavía en cocina la mesa no se cobra', (tester) async {
    final api = ApiFalsa(_salaTipica().call);
    await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel(RegExp(r'^Mesa 2,')));
    await tester.pumpAndSettle();

    expect(
      find.text('Espere a que cocina entregue todo antes de cobrar.'),
      findsOneWidget,
    );
    expect(find.text('Sin documento'), findsNothing);
  });

  testWidgets('la pre-cuenta impresa lleva el total de la mesa', (
    tester,
  ) async {
    final api = ApiFalsa(_salaTipica().call);
    final m = await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();
    await _abrirCuentaMesa3(tester);

    await tester.tap(find.text('Imprimir pre-cuenta'));
    await tester.pump();

    final html = m.plataforma.impresiones.single;
    expect(html, contains('PRE-CUENTA'));
    expect(html, contains('S/ 95.00'));
    expect(html, isNot(contains('<script')));
  });

  testWidgets('el admin crea una mesa desde Gestionar mesas', (tester) async {
    final api = ApiFalsa(_salaTipica().call);
    await montar(tester, const MesasPage(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Gestionar mesas'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Nueva mesa'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Número de mesa'),
      '9',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Ubicación (opcional)'),
      'Patio',
    );
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/mesas'), {
      'numero': 9,
      'capacidad': 4,
      'ubicacion': 'Patio',
    });
  });

  testWidgets('el personal no ve Gestionar mesas', (tester) async {
    final api = ApiFalsa(_salaTipica().call);
    await montar(
      tester,
      const MesasPage(),
      api: api,
      usuario: usuarioDePrueba(roles: ['mozo']),
    );
    await tester.pumpAndSettle();

    expect(find.text('Gestionar mesas'), findsNothing);
    expect(find.text('Atiendo solo'), findsNothing);
  });
}
