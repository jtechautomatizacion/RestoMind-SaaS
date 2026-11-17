import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:restomind/core/api/api_client.dart';
import 'package:restomind/core/plataforma/plataforma_base.dart';
import 'package:restomind/core/servicios.dart';
import 'package:restomind/core/sesion.dart';
import 'package:restomind/core/roles.dart';
import 'package:restomind/design/tema.dart';
import 'package:restomind/shell/caja_gate.dart';
import 'package:restomind/shell/shell.dart';

/// Apoyo COMPARTIDO de las pruebas: una API falsa, una sesión ya iniciada y la
/// pantalla montada con el tema y los scopes de la app. Ninguna prueba toca la
/// red ni un backend real.

/// Respuesta falsa: (estado, cuerpo JSON).
typedef Ruteo = (int, Object?) Function(http.Request req);

/// Registro de lo que la pantalla le pidió a la API, para afirmar sobre ello.
class ApiFalsa {
  ApiFalsa(this.ruteo);

  final Ruteo ruteo;
  final List<http.Request> pedidos = [];

  late final ApiClient api = ApiClient(
    base: '',
    cliente: MockClient((req) async {
      pedidos.add(req);
      final (estado, cuerpo) = ruteo(req);
      return http.Response(
        cuerpo == null ? '' : jsonEncode(cuerpo),
        estado,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }),
  )..fijarToken('token-de-prueba');

  /// Pedidos a una ruta (sin /api), p. ej. `llamadas('POST', '/comandas')`.
  List<http.Request> llamadas(String metodo, String ruta) => pedidos
      .where((r) => r.method == metodo && r.url.path == '/api$ruta')
      .toList();

  /// Cuerpo JSON del último pedido a esa ruta.
  Map<String, dynamic> cuerpo(String metodo, String ruta) =>
      jsonDecode(llamadas(metodo, ruta).last.body) as Map<String, dynamic>;
}

Usuario usuarioDePrueba({
  List<String> roles = const ['admin'],
  bool usarSunat = true,
  bool emiteFacturas = false,
}) => Usuario(
  email: 'admin@test.local',
  nombre: 'Admin de prueba',
  rol: roles.join(','),
  roles: roles,
  clienteId: 'test-cliente-001',
  clienteNombre: 'Restaurante de Prueba',
  clienteRuc: '20000000001',
  usarSunat: usarSunat,
  emiteFacturas: emiteFacturas,
);

/// Monta [pantalla] como la vería un usuario logueado con [usuario].
Future<
  ({
    Servicios servicios,
    PlataformaMemoria plataforma,
    List<(Pestana, String?)> navegaciones,
  })
>
montar(
  dynamic tester,
  Widget pantalla, {
  required ApiFalsa api,
  Usuario? usuario,
  Brightness brillo = Brightness.dark,
}) async {
  final plataforma = PlataformaMemoria();
  final sesion = Sesion(api.api)
    ..usuario = usuario ?? usuarioDePrueba()
    ..estado = EstadoSesion.autenticada;
  final servicios = Servicios(
    api: api.api,
    sesion: sesion,
    plataforma: plataforma,
  );
  final navegaciones = <(Pestana, String?)>[];
  await tester.pumpWidget(
    ServiciosScope(
      servicios: servicios,
      child: MaterialApp(
        theme: temaRestoMind(brillo),
        home: ShellScope(
          ir: (p, {seccion}) => navegaciones.add((p, seccion)),
          cajaGate: CajaGate(api.api),
          child: Scaffold(body: pantalla),
        ),
      ),
    ),
  );
  return (
    servicios: servicios,
    plataforma: plataforma,
    navegaciones: navegaciones,
  );
}
