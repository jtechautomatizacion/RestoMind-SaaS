import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/core/plataforma/plataforma.dart';
import 'package:restomind/core/plataforma/plataforma_base.dart';
import 'package:restomind/core/servicios.dart';
import 'package:restomind/core/sesion.dart';
import 'package:restomind/design/tema.dart';

import '../../../apoyo.dart';

/// PNG de 1×1: bytes reales, para que la vista previa no falle al decodificar.
const pngMinimo = [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, //
  0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
  0x0D, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
];

/// Plataforma de pruebas cuyo selector de archivos "elige" una foto.
class PlataformaConFoto extends PlataformaMemoria {
  @override
  Future<ArchivoElegido?> elegirImagen() async =>
      const ArchivoElegido(pngMinimo, 'foto.png');
}

/// Como `montar()` de apoyo.dart, pero con [PlataformaConFoto]: `montar()`
/// arma su propia plataforma y no deja cambiarla.
Future<void> montarConFoto(
  WidgetTester tester,
  Widget pantalla, {
  required ApiFalsa api,
}) => tester.pumpWidget(
  ServiciosScope(
    servicios: Servicios(
      api: api.api,
      sesion: Sesion(api.api)
        ..usuario = usuarioDePrueba()
        ..estado = EstadoSesion.autenticada,
      plataforma: PlataformaConFoto(),
    ),
    child: MaterialApp(
      theme: temaRestoMind(Brightness.dark),
      home: Scaffold(body: pantalla),
    ),
  ),
);
