import 'dart:async';
import 'dart:js_interop';
import 'dart:typed_data';

import 'package:http/browser_client.dart';
import 'package:http/http.dart' as http;
import 'package:web/web.dart' as web;

import 'plataforma.dart';

Plataforma crearPlataforma() => _PlataformaWeb();

class _PlataformaWeb implements Plataforma {
  static const _prefijo = 'restomind.pref.';

  @override
  http.Client clienteHttp() => BrowserClient()..withCredentials = true;

  @override
  Future<void> descargar(List<int> bytes, String nombre, String tipo) async {
    final blob = web.Blob(
      [Uint8List.fromList(bytes).toJS].toJS,
      web.BlobPropertyBag(type: tipo),
    );
    final url = web.URL.createObjectURL(blob);
    final a = web.HTMLAnchorElement()
      ..href = url
      ..download = nombre;
    web.document.body!.append(a);
    a.click();
    a.remove();
    Timer(const Duration(seconds: 30), () => web.URL.revokeObjectURL(url));
  }

  @override
  Future<void> imprimirHtml(String html) async {
    // Un iframe oculto con srcdoc: es del mismo origen, así que se le puede
    // pedir print() desde acá sin un script adentro del documento.
    final marco = web.HTMLIFrameElement()
      ..style.position = 'fixed'
      ..style.width = '0'
      ..style.height = '0'
      ..style.border = '0'
      ..style.visibility = 'hidden'
      ..srcdoc = html.toJS;
    final listo = Completer<void>();
    marco.onload = ((web.Event _) {
      if (!listo.isCompleted) listo.complete();
    }).toJS;
    web.document.body!.append(marco);
    await listo.future.timeout(const Duration(seconds: 5), onTimeout: () {});
    marco.contentWindow?.focus();
    marco.contentWindow?.print();
    // El diálogo de impresión es bloqueante en casi todos los navegadores; el
    // margen es para los que no lo son.
    Timer(const Duration(minutes: 1), () => marco.remove());
  }

  @override
  Future<ArchivoElegido?> elegirImagen() =>
      elegirArchivo(aceptar: 'image/jpeg,image/png,image/webp');

  @override
  Future<ArchivoElegido?> elegirArchivo({required String aceptar}) async {
    final input = web.HTMLInputElement()
      ..type = 'file'
      ..accept = aceptar;
    final resultado = Completer<ArchivoElegido?>();
    input.onchange = ((web.Event _) {
      final archivo = input.files?.item(0);
      if (archivo == null) {
        resultado.complete(null);
        return;
      }
      final lector = web.FileReader();
      lector.onload = ((web.Event _) {
        final buffer = (lector.result as JSArrayBuffer?)?.toDart;
        resultado.complete(
          buffer == null
              ? null
              : ArchivoElegido(buffer.asUint8List(), archivo.name),
        );
      }).toJS;
      lector.onerror = ((web.Event _) => resultado.complete(null)).toJS;
      lector.readAsArrayBuffer(archivo);
    }).toJS;
    input.click();
    return resultado.future;
  }

  @override
  String? preferencia(String clave) {
    try {
      return web.window.localStorage.getItem('$_prefijo$clave');
    } catch (_) {
      return null; // Navegación privada o almacenamiento bloqueado.
    }
  }

  @override
  void guardarPreferencia(String clave, String? valor) {
    try {
      if (valor == null) {
        web.window.localStorage.removeItem('$_prefijo$clave');
      } else {
        web.window.localStorage.setItem('$_prefijo$clave', valor);
      }
    } catch (_) {
      // Sin almacenamiento la preferencia dura lo que la pestaña.
    }
  }

  @override
  void irA(String ruta) => web.window.location.assign(ruta);
}
