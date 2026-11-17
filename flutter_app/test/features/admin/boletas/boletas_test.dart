import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/core/plataforma/plataforma.dart';
import 'package:restomind/features/admin/boletas/boletas_seccion.dart';

import '../../../apoyo.dart';

Map<String, dynamic> _cfg({required bool usarSunat, bool tieneRuc = true}) => {
  'usar_sunat': usarSunat,
  'tiene_ruc': tieneRuc,
  'ruc': tieneRuc ? '20000000001' : null,
  'razon_social': tieneRuc ? 'RESTO SAC' : null,
  'datos_fiscales_bloqueados': usarSunat,
  'emite_facturas': false,
  'es_ambiente_beta': false,
};

Map<String, dynamic> _comprobante({String estado = 'aceptado'}) => {
  'id': 7,
  'numero_mesa': 4,
  'serie': 'B001',
  'numero_correlativo': 12,
  'numero_boleta': 'B001-00000012',
  'subtotal': 25.42,
  'igv': 4.58,
  'total': 30.0,
  'estado': estado,
  'creado_en': '2026-11-17T15:00:00',
  'fecha_emision_local': '2026-11-17',
  'hora_emision_local': '10:00:00',
  'ruc_emisor': '20000000001',
  'razon_social_emisor': 'RESTO SAC',
  'nombre_emisor': 'Resto',
  'tipo_documento_comprador': '0',
  'numero_documento_comprador': '-',
  'nombre_comprador': 'CLIENTES VARIOS',
  'detalles': [
    {
      'descripcion': 'Ceviche',
      'cantidad': 1,
      'precio_unitario': 30.0,
      'subtotal': 30.0,
    },
  ],
};

const _pendientes = {
  'facturas_con_error': [
    {
      'id': 7,
      'numero_boleta': 'B001-00000012',
      'numero_mesa': 4,
      'total': 30.0,
      'estado': 'error',
      'error_mensaje': 'SUNAT no respondió',
      'creado_en': '2026-11-17T15:00:00',
    },
  ],
  'ventas_sin_boleta': [
    {
      'numero_mesa': 2,
      'comanda_ids': [31, 32],
      'total': 54.5,
      'creado_en': '2026-11-17T16:00:00',
    },
  ],
};

const _me = {
  'email': 'admin@test.local',
  'nombre': 'Admin de prueba',
  'rol': 'admin',
  'roles': ['admin'],
  'cliente_id': 'test-cliente-001',
  'cliente_nombre': 'Restaurante de Prueba',
  'cliente_usar_sunat': false,
};

ApiFalsa _api({
  required Map<String, dynamic> cfg,
  Object pendientes = const {
    'facturas_con_error': <Object>[],
    'ventas_sin_boleta': <Object>[],
  },
  (int, Object?)? alReintentar,
}) => ApiFalsa((req) {
  return switch ((req.method, req.url.path)) {
    ('GET', '/api/configuracion') => (200, cfg),
    ('PATCH', '/api/configuracion') => (
      200,
      {...cfg, 'usar_sunat': req.body.contains('true')},
    ),
    ('GET', '/api/facturas/pendientes') => (200, pendientes),
    ('POST', '/api/facturas/7/reintentar') =>
      alReintentar ?? (200, _comprobante()),
    ('POST', '/api/facturas/generar') => (201, _comprobante()),
    ('GET', '/api/auth/me') => (200, _me),
    _ => (404, {'detail': 'no'}),
  };
});

Future<void> _pantallaGrande(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

final _switch = find.byKey(const ValueKey('switch-facturacion'));

void main() {
  testWidgets('la primera activación pide el certificado y lo sube todo junto', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    final cfg = {
      ..._cfg(usarSunat: false, tieneRuc: false),
      'es_ambiente_beta': true,
    };
    final api = ApiFalsa((req) {
      return switch ((req.method, req.url.path)) {
        ('GET', '/api/configuracion') => (200, cfg),
        ('GET', '/api/facturas/pendientes') => (
          200,
          {'facturas_con_error': <Object>[], 'ventas_sin_boleta': <Object>[]},
        ),
        ('GET', '/api/documento/20000000001') => (
          200,
          {'documento': '20000000001', 'tipo': 'RUC', 'encontrado': false},
        ),
        ('POST', '/api/configuracion/subir-certificado') => (
          200,
          {..._cfg(usarSunat: true), 'datos_fiscales_bloqueados': true},
        ),
        ('GET', '/api/auth/me') => (200, {..._me, 'cliente_usar_sunat': true}),
        _ => (404, {'detail': 'no'}),
      };
    });
    final m = await montar(tester, const BoletasSeccion(), api: api);
    m.plataforma.archivoAElegir = const ArchivoElegido([1, 2, 3], 'cert.pfx');
    await tester.pumpAndSettle();

    await tester.tap(_switch);
    await tester.pumpAndSettle();
    // Prender por primera vez NO es un PATCH: abre el asistente.
    expect(api.llamadas('PATCH', '/configuracion'), isEmpty);
    expect(find.text('Activar boletas electrónicas'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextField, 'RUC del restaurante'),
      '20000000001',
    );
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Razón social'),
      'RESTO PRUEBAS SAC',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Dirección fiscal'),
      'Av. Lima 123',
    );
    await tester.tap(find.text('Continuar'));
    await tester.pumpAndSettle();

    // Restaurante de pruebas: las credenciales públicas de BETA ya vienen puestas.
    expect(find.text('MODDATOS'), findsOneWidget);
    await tester.tap(find.text('Vincular con SUNAT'));
    await tester.pumpAndSettle();
    expect(find.text('Falta el certificado (.pfx).'), findsOneWidget);

    await tester.tap(find.text('Elegir certificado digital (.pfx)'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Clave del certificado'),
      'clave-pfx',
    );
    await tester.tap(find.text('Vincular con SUNAT'));
    await tester.pumpAndSettle();

    final subida = api
        .llamadas('POST', '/configuracion/subir-certificado')
        .single;
    final cuerpo = utf8.decode(subida.bodyBytes);
    for (final campo in [
      'name="ruc"',
      'name="password"',
      'name="sol_usuario"',
      'name="sol_clave"',
      'name="direccion_fiscal"',
      'name="razon_social_manual"',
      'name="file"; filename="cert.pfx"',
    ]) {
      expect(cuerpo, contains(campo));
    }
    expect(cuerpo, contains('RESTO PRUEBAS SAC'));
    expect(api.llamadas('GET', '/auth/me'), hasLength(1));
    expect(tester.widget<Switch>(_switch).value, isTrue);
  });

  testWidgets('apagar la facturación la guarda y relee la identidad', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    final api = _api(cfg: _cfg(usarSunat: true));
    final m = await montar(tester, const BoletasSeccion(), api: api);
    await tester.pumpAndSettle();
    expect(m.servicios.sesion.usuario!.usarSunat, isTrue);

    await tester.tap(_switch);
    await tester.pumpAndSettle();

    expect(api.cuerpo('PATCH', '/configuracion'), {'usar_sunat': false});
    expect(api.llamadas('GET', '/auth/me'), hasLength(1));
    expect(m.servicios.sesion.usuario!.usarSunat, isFalse);
    expect(tester.widget<Switch>(_switch).value, isFalse);
    expect(find.text('Boletas desactivadas'), findsOneWidget);
  });

  testWidgets(
    'volver a prender algo ya configurado pide confirmación y hace PATCH',
    (tester) async {
      await _pantallaGrande(tester);
      final api = _api(
        cfg: {..._cfg(usarSunat: false), 'datos_fiscales_bloqueados': true},
      );
      await montar(tester, const BoletasSeccion(), api: api);
      await tester.pumpAndSettle();

      await tester.tap(_switch);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cancelar'));
      await tester.pumpAndSettle();
      expect(api.llamadas('PATCH', '/configuracion'), isEmpty);

      await tester.tap(_switch);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Activar'));
      await tester.pumpAndSettle();
      expect(api.cuerpo('PATCH', '/configuracion'), {'usar_sunat': true});
      expect(api.llamadas('GET', '/auth/me'), hasLength(1));
    },
  );

  testWidgets('lista lo que quedó sin emitir', (tester) async {
    await _pantallaGrande(tester);
    await montar(
      tester,
      const BoletasSeccion(),
      api: _api(cfg: _cfg(usarSunat: true), pendientes: _pendientes),
    );
    await tester.pumpAndSettle();

    expect(find.text('Boletas con error (1)'), findsOneWidget);
    expect(find.text('B001-00000012'), findsOneWidget);
    expect(find.text('SUNAT no respondió'), findsOneWidget);
    expect(find.text('Ventas sin boleta (1)'), findsOneWidget);
    expect(find.text('Mesa 2'), findsOneWidget);
  });

  testWidgets('reintentar emite con el mismo número e imprime la boleta', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    final api = _api(cfg: _cfg(usarSunat: true), pendientes: _pendientes);
    final m = await montar(tester, const BoletasSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();

    expect(api.llamadas('POST', '/facturas/7/reintentar'), hasLength(1));
    expect(find.text('Boleta B001-00000012 emitida'), findsOneWidget);
    expect(m.plataforma.impresiones, hasLength(1));
    expect(m.plataforma.impresiones.single, contains('B001-00000012'));
    expect(
      m.plataforma.impresiones.single,
      contains('Representación impresa del comprobante'),
    );
  });

  testWidgets('si sigue fallando, imprime la contingencia que trae el error', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    final api = _api(
      cfg: _cfg(usarSunat: true),
      pendientes: _pendientes,
      alReintentar: (
        502,
        {
          'detail': {
            'mensaje': 'Sigue sin poder generarse esta boleta',
            'factura': _comprobante(estado: 'error'),
          },
        },
      ),
    );
    final m = await montar(tester, const BoletasSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();

    expect(m.plataforma.impresiones.single, contains('NO ES COMPROBANTE'));
    expect(find.textContaining('Sigue pendiente'), findsOneWidget);
  });

  testWidgets('emitir una venta sin boleta manda sus comandas', (tester) async {
    await _pantallaGrande(tester);
    final api = _api(cfg: _cfg(usarSunat: true), pendientes: _pendientes);
    final m = await montar(tester, const BoletasSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Emitir'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/facturas/generar'), {
      'comanda_ids': [31, 32],
    });
    expect(m.plataforma.impresiones, hasLength(1));
  });
}
