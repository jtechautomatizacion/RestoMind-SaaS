import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:restomind/core/api/api_client.dart';
import 'package:restomind/core/api/api_error.dart';
import 'package:restomind/core/formato.dart';
import 'package:restomind/core/roles.dart';
import 'package:restomind/core/sesion.dart';

Map<String, dynamic> _usuario() => {
  'email': 'admin@test.local',
  'nombre': 'Admin',
  'rol': 'admin',
  'roles': ['admin'],
  'cliente_id': 'c1',
  'cliente_nombre': 'Resto',
};

void main() {
  group('ApiClient — sesión al estilo Sac-Geo', () {
    test(
      'un 401 renueva UNA vez aunque lleguen varias peticiones a la vez',
      () async {
        var refreshes = 0;
        final api = ApiClient(
          base: '',
          cliente: MockClient((req) async {
            if (req.url.path == '/api/auth/sesion/refresh') {
              refreshes++;
              await Future<void>.delayed(const Duration(milliseconds: 10));
              return http.Response(
                jsonEncode({'access_token': 'nuevo', 'usuario': _usuario()}),
                200,
              );
            }
            final ok = req.headers['Authorization'] == 'Bearer nuevo';
            return http.Response(
              ok ? '[]' : '{"detail":"expirado"}',
              ok ? 200 : 401,
            );
          }),
        )..fijarToken('viejo');

        await Future.wait([
          api.get('/mesas'),
          api.get('/platos'),
          api.get('/comandas'),
        ]);
        expect(refreshes, 1);
      },
    );

    test('si la renovación falla, avisa que la sesión caducó', () async {
      var caducada = false;
      final api =
          ApiClient(
              base: '',
              cliente: MockClient(
                (req) async => http.Response('{"detail":"no"}', 401),
              ),
            )
            ..fijarToken('viejo')
            ..alCaducarSesion = () => caducada = true;

      await expectLater(
        api.get('/mesas'),
        throwsA(isA<ApiError>().having((e) => e.status, 'status', 401)),
      );
      expect(caducada, isTrue);
      expect(api.tieneToken, isFalse);
    });

    test('el login pide el modo cookie y nunca manda Authorization', () async {
      late http.Request login;
      final api = ApiClient(
        base: '',
        cliente: MockClient((req) async {
          login = req;
          return http.Response(
            jsonEncode({'access_token': 't', 'usuario': _usuario()}),
            200,
          );
        }),
      );
      await api.entrar('/auth/login', {'email': 'a', 'password': 'b'});
      expect(login.headers['X-Sesion'], 'cookie');
      expect(login.headers.containsKey('Authorization'), isFalse);
      expect(api.tieneToken, isTrue);
    });

    test('manda la zona horaria del aparato', () async {
      late http.Request r;
      final api = ApiClient(
        base: '',
        cliente: MockClient((req) async {
          r = req;
          return http.Response('{}', 200);
        }),
      )..fijarToken('t');
      await api.get('/caja/gate');
      expect(
        r.headers['X-TZ-Offset'],
        '${-DateTime.now().timeZoneOffset.inMinutes}',
      );
    });
  });

  group('ApiError', () {
    test('lee los tres formatos de detail de FastAPI', () {
      expect(
        ApiError.desdeRespuesta(400, {'detail': 'Mesa ocupada'}).mensaje,
        'Mesa ocupada',
      );
      expect(
        ApiError.desdeRespuesta(422, {
          'detail': [
            {'msg': 'Campo requerido'},
          ],
        }).mensaje,
        'Campo requerido',
      );
      final e = ApiError.desdeRespuesta(400, {
        'detail': {
          'codigo': 'IDENTIFICAR_COMPRADOR',
          'mensaje': 'Identifique al cliente',
        },
      });
      expect(e.codigo, 'IDENTIFICAR_COMPRADOR');
      expect(e.mensaje, 'Identifique al cliente');
    });
  });

  group('roles — espejo de backend/utils/roles.py', () {
    test('las pestañas son la unión de los roles', () {
      expect(pestanasDe(['cajero', 'jefe_cocina']), [
        Pestana.mesas,
        Pestana.cocina,
      ]);
      expect(pestanasDe(['admin']), Pestana.values);
      expect(pestanasDe(['asistente']), [Pestana.mesas, Pestana.cocina]);
    });

    test('solo admin y asistente ven "Atiendo solo"', () {
      expect(veVistaUnificada(['admin']), isTrue);
      expect(veVistaUnificada(['asistente']), isTrue);
      expect(veVistaUnificada(['cajero', 'jefe_cocina']), isFalse);
    });

    test('el cajero en solitario solo cobra', () {
      expect(soloCobra(['cajero']), isTrue);
      expect(soloCobra(['cajero', 'mozo']), isFalse);
      expect(soloCobra(['cajero', 'jefe_cocina']), isTrue);
    });

    test('Usuario lee la identidad del backend', () {
      final u = Usuario.desdeJson({..._usuario(), 'cliente_usar_sunat': true});
      expect(u.esAdmin, isTrue);
      expect(u.usarSunat, isTrue);
      expect(u.pestanas, Pestana.values);
    });
  });

  group('formato', () {
    test('soles nunca redondea', () {
      expect(soles(122.5), 'S/ 122.50');
      expect(soles(1284.5), 'S/ 1,284.50');
      expect(soles(-5), 'S/ -5.00');
      expect(soles(1234567.891), 'S/ 1,234,567.89');
    });

    test('las esperas largas se leen en horas o días', () {
      expect(duracion(8), '8 min');
      expect(duracion(60), '1 h');
      expect(duracion(135), '2 h 15 min');
      expect(duracion(85515), '59 d');
    });

    test('las fechas del backend se leen como UTC', () {
      final f = fechaLocal('2026-11-17T15:00:00')!;
      expect(f.toUtc().hour, 15);
      expect(fechaLocal(null), isNull);
    });
  });
}
