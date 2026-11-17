import 'package:http/http.dart' as http;

import 'plataforma.dart';

/// Fuera del navegador (pruebas en la VM). Sin efectos: lo que necesita el DOM
/// no hace nada, y las preferencias viven en memoria.
Plataforma crearPlataforma() => PlataformaMemoria();

class PlataformaMemoria implements Plataforma {
  final Map<String, String> _prefs = {};
  final List<String> impresiones = [];
  final List<String> descargas = [];
  String? ultimaNavegacion;

  @override
  http.Client clienteHttp() => http.Client();

  @override
  Future<void> descargar(List<int> bytes, String nombre, String tipo) async =>
      descargas.add(nombre);

  @override
  Future<void> imprimirHtml(String html) async => impresiones.add(html);

  /// Lo que devuelven los selectores de archivo en las pruebas.
  ArchivoElegido? archivoAElegir;

  @override
  Future<ArchivoElegido?> elegirImagen() async => archivoAElegir;

  @override
  Future<ArchivoElegido?> elegirArchivo({required String aceptar}) async =>
      archivoAElegir;

  @override
  String? preferencia(String clave) => _prefs[clave];

  @override
  void guardarPreferencia(String clave, String? valor) =>
      valor == null ? _prefs.remove(clave) : _prefs[clave] = valor;

  @override
  void irA(String ruta) => ultimaNavegacion = ruta;
}
