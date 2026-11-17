import 'package:http/http.dart' as http;

import 'plataforma_base.dart'
    if (dart.library.js_interop) 'plataforma_web.dart';

/// Un archivo elegido por el usuario (la foto de un plato).
class ArchivoElegido {
  const ArchivoElegido(this.bytes, this.nombre);
  final List<int> bytes;
  final String nombre;
}

/// Lo que cambia entre el navegador y el resto (pruebas en la VM, y Android
/// cuando llegue). Las pantallas solo hablan con esta interfaz.
abstract class Plataforma {
  factory Plataforma() => crearPlataforma();

  /// En web: BrowserClient con withCredentials, para la cookie de refresh.
  http.Client clienteHttp();

  /// Guarda bytes como un archivo descargado (el Excel del dashboard).
  Future<void> descargar(List<int> bytes, String nombre, String tipo);

  /// Imprime un documento HTML con el diálogo del sistema (pre-cuenta,
  /// comprobante, reporte de caja). Sin ventanas nuevas ni scripts inline:
  /// la CSP de la app no los permite.
  Future<void> imprimirHtml(String html);

  /// Abre el selector de archivos del sistema para una foto. null si se canceló.
  Future<ArchivoElegido?> elegirImagen();

  /// Selector de archivos para otros tipos ([aceptar] como en `<input accept>`,
  /// p. ej. '.pfx,.p12' para el certificado digital). null si se canceló.
  Future<ArchivoElegido?> elegirArchivo({required String aceptar});

  /// Preferencias de ESTE aparato (tema, vista "Atiendo solo"). Nunca datos
  /// de sesión ni nada sensible: eso vive solo en memoria.
  String? preferencia(String clave);
  void guardarPreferencia(String clave, String? valor);

  /// Navega fuera de la app (p. ej. al panel general del superadmin).
  void irA(String ruta);
}
