import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/features/admin/personal/modelos.dart';
import 'package:restomind/features/admin/personal/personal_seccion.dart';

import '../../../apoyo.dart';

Map<String, dynamic> _admin() => {
  'id': 'usr-admin',
  'nombre': 'Dueño',
  'email': 'admin@test.local',
  'celular': null,
  'rol': 'admin',
  'roles': ['admin'],
  'estado': 'activo',
  'creado_en': '2026-11-01T10:00:00',
};

Map<String, dynamic> _staff({
  String id = 'usr-1',
  String nombre = 'Pedro',
  String codigo = '112233',
  List<String> roles = const ['mozo'],
}) => {
  'id': id,
  'nombre': nombre,
  'email': null,
  'celular': codigo,
  'rol': roles.join(','),
  'roles': roles,
  'estado': 'activo',
  'creado_en': '2026-11-01T10:00:00',
};

/// API con el personal en memoria: lo que se crea aparece en la lista.
ApiFalsa _api({(int, Object?)? alEditar}) {
  final personal = [_admin(), _staff()];
  return ApiFalsa((req) {
    final ruta = req.url.path;
    if (req.method == 'GET' && ruta == '/api/usuarios') return (200, personal);
    if (req.method == 'POST' && ruta == '/api/usuarios/staff') {
      final b = jsonDecode(req.body) as Map<String, dynamic>;
      final nuevo = _staff(
        id: 'usr-nuevo',
        nombre: b['nombre'] as String,
        codigo: '483920',
        roles: [for (final r in b['roles'] as List<dynamic>) '$r'],
      );
      personal.add(nuevo);
      return (201, nuevo);
    }
    if (req.method == 'PATCH') return alEditar ?? (200, _staff());
    if (req.method == 'DELETE') return (204, null);
    return (404, {'detail': 'no'});
  });
}

Future<void> _pantallaGrande(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

SwitchListTile _rol(WidgetTester tester, String rol) =>
    tester.widget<SwitchListTile>(find.byKey(ValueKey('rol-$rol')));

void main() {
  group('rolBloqueado', () {
    test('asistente bloquea los demás, y cualquier otro bloquea asistente', () {
      expect(rolBloqueado('mozo', {'asistente'}), isTrue);
      expect(rolBloqueado('asistente', {'asistente'}), isFalse);
      expect(rolBloqueado('asistente', {'cajero'}), isTrue);
      expect(rolBloqueado('jefe_cocina', {'cajero'}), isFalse);
      expect(rolBloqueado('asistente', {}), isFalse);
    });
  });

  testWidgets('lista: el admin es "Tú", sin eliminar; el personal con código', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    await montar(tester, const PersonalSeccion(), api: _api());
    await tester.pumpAndSettle();

    expect(find.text('Tú'), findsOneWidget);
    expect(find.text('admin@test.local'), findsOneWidget);
    expect(find.textContaining('112233', findRichText: true), findsOneWidget);
    // Solo Pedro se puede eliminar.
    expect(find.byTooltip('Eliminar'), findsOneWidget);
  });

  testWidgets('crear personal manda nombre, contraseña y roles, y muestra el '
      'código que generó el backend', (tester) async {
    await _pantallaGrande(tester);
    final api = _api();
    await montar(tester, const PersonalSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nueva cuenta'));
    await tester.pumpAndSettle();
    expect(find.text('Administrador (no editable)'), findsNothing);
    expect(find.byKey(const ValueKey('rol-admin')), findsNothing);

    await tester.enterText(
      find.widgetWithText(TextFormField, 'Nombre'),
      'Rosa',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Contraseña'),
      'secreta1',
    );
    await tester.tap(find.byKey(const ValueKey('rol-cajero')));
    await tester.tap(find.byKey(const ValueKey('rol-jefe_cocina')));
    await tester.pump();
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('POST', '/usuarios/staff'), {
      'nombre': 'Rosa',
      'password': 'secreta1',
      'roles': ['cajero', 'jefe_cocina'],
    });
    expect(find.text('Cuenta creada'), findsOneWidget);
    expect(find.text('483920'), findsOneWidget);

    await tester.tap(find.text('Listo'));
    await tester.pumpAndSettle();
    expect(find.textContaining('483920', findRichText: true), findsOneWidget);
  });

  testWidgets('sin ningún rol no se crea la cuenta', (tester) async {
    await _pantallaGrande(tester);
    final api = _api();
    await montar(tester, const PersonalSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.text('Nueva cuenta'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Nombre'),
      'Rosa',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Contraseña'),
      'secreta1',
    );
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();

    expect(api.llamadas('POST', '/usuarios/staff'), isEmpty);
    expect(find.text('Marque al menos un rol'), findsOneWidget);
  });

  testWidgets('asistente apaga y bloquea los demás roles, y al revés', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    await montar(tester, const PersonalSeccion(), api: _api());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Nueva cuenta'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('rol-asistente')));
    await tester.pump();
    for (final r in ['mozo', 'cajero', 'jefe_cocina']) {
      expect(_rol(tester, r).onChanged, isNull, reason: r);
    }
    expect(_rol(tester, 'asistente').value, isTrue);

    await tester.tap(find.byKey(const ValueKey('rol-asistente')));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('rol-mozo')));
    await tester.pump();
    expect(_rol(tester, 'asistente').onChanged, isNull);
    expect(_rol(tester, 'cajero').onChanged, isNotNull);
  });

  testWidgets('editar personal manda nombre, roles y estado', (tester) async {
    await _pantallaGrande(tester);
    final api = _api();
    await montar(tester, const PersonalSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Editar').last);
    await tester.pumpAndSettle();
    expect(find.text('Código de acceso'), findsOneWidget);
    await tester.tap(find.text('Cuenta activa'));
    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();

    expect(api.llamadas('PATCH', '/usuarios/usr-1'), hasLength(1));
    expect(api.cuerpo('PATCH', '/usuarios/usr-1'), {
      'nombre': 'Pedro',
      'roles': ['mozo'],
      'estado': 'inactivo',
    });
    expect(find.text('Cuenta actualizada'), findsOneWidget);
  });

  testWidgets('el admin solo edita su nombre, y el rechazo de la API se ve', (
    tester,
  ) async {
    await _pantallaGrande(tester);
    final api = _api(
      alEditar: (400, {'detail': 'No puedes quitarte tu propio rol'}),
    );
    await montar(tester, const PersonalSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Editar').first);
    await tester.pumpAndSettle();
    expect(find.text('Administrador (no editable)'), findsOneWidget);
    expect(find.byKey(const ValueKey('rol-mozo')), findsNothing);
    expect(find.text('Cuenta activa'), findsNothing);

    await tester.tap(find.text('Guardar'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('PATCH', '/usuarios/usr-admin'), {'nombre': 'Dueño'});
    expect(find.text('No puedes quitarte tu propio rol'), findsOneWidget);
    // El formulario sigue abierto con lo escrito.
    expect(find.text('Editar cuenta'), findsOneWidget);
  });

  testWidgets('resetear contraseña', (tester) async {
    await _pantallaGrande(tester);
    final api = _api();
    await montar(tester, const PersonalSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Resetear contraseña').last);
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField), 'nueva123');
    await tester.tap(find.text('Guardar nueva contraseña'));
    await tester.pumpAndSettle();

    expect(api.cuerpo('PATCH', '/usuarios/usr-1/password'), {
      'nueva_password': 'nueva123',
    });
    expect(find.text('Contraseña actualizada'), findsOneWidget);
  });

  testWidgets('eliminar pide confirmación', (tester) async {
    await _pantallaGrande(tester);
    final api = _api();
    await montar(tester, const PersonalSeccion(), api: api);
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Eliminar'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancelar'));
    await tester.pumpAndSettle();
    expect(api.llamadas('DELETE', '/usuarios/usr-1'), isEmpty);

    await tester.tap(find.byTooltip('Eliminar'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Eliminar'));
    await tester.pumpAndSettle();
    expect(api.llamadas('DELETE', '/usuarios/usr-1'), hasLength(1));
  });
}
