import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_error.dart';

/// Un archivo bajado de la API (el Excel del dashboard).
class Descarga {
  const Descarga(this.bytes, this.nombre, this.tipo);
  final List<int> bytes;
  final String nombre;
  final String tipo;
}

/// Cliente HTTP ÚNICO de la aplicación. Mismo contrato de sesión que Sac-Geo:
///
///  · el access token vive SOLO en memoria (este objeto): nunca en
///    localStorage, sessionStorage ni IndexedDB;
///  · el refresh es la cookie HttpOnly `__Secure-restomind_refresh`, con
///    `Path=/api/auth/sesion`: la maneja el navegador y este código nunca la ve.
///    En web el cliente es un BrowserClient con `withCredentials`;
///  · un 401 en una llamada autenticada dispara UNA renovación. Las peticiones
///    que llegan mientras tanto esperan esa misma renovación: dos refresh con la
///    misma cookie se tomarían como reuso y el servidor cerraría la sesión.
class ApiClient {
  ApiClient({required this.base, required http.Client cliente})
    : _http = cliente;

  /// Origen de la API. Vacío = el mismo origen desde el que se sirve la app,
  /// que es lo que exige la cookie SameSite=Strict.
  final String base;
  final http.Client _http;

  String? _token;
  Future<Map<String, dynamic>?>? _renovacion;

  /// Se llama cuando la sesión no se pudo renovar (vuelta al login).
  void Function()? alCaducarSesion;

  /// Se llama con la identidad fresca cada vez que la sesión se renueva.
  void Function(Map<String, dynamic> usuario)? alRenovar;

  bool get tieneToken => _token != null;
  void fijarToken(String? token) => _token = token;

  // ------------------------------------------------------------ verbos ----

  Future<dynamic> get(String ruta, {Map<String, Object?> query = const {}}) =>
      _json('GET', ruta, query: query);

  Future<dynamic> post(String ruta, [Object? cuerpo]) =>
      _json('POST', ruta, cuerpo: cuerpo ?? const <String, dynamic>{});

  Future<dynamic> patch(String ruta, [Object? cuerpo]) =>
      _json('PATCH', ruta, cuerpo: cuerpo ?? const <String, dynamic>{});

  Future<dynamic> put(String ruta, [Object? cuerpo]) =>
      _json('PUT', ruta, cuerpo: cuerpo ?? const <String, dynamic>{});

  Future<dynamic> delete(String ruta, [Object? cuerpo]) =>
      _json('DELETE', ruta, cuerpo: cuerpo);

  /// Login: sin token, y pidiendo el modo de sesión con cookie.
  Future<Map<String, dynamic>> entrar(
    String ruta,
    Map<String, Object?> credenciales,
  ) async {
    final r = await _enviar(
      'POST',
      ruta,
      cuerpo: credenciales,
      autenticada: false,
      extra: const {'X-Sesion': 'cookie'},
    );
    if (r.statusCode >= 400) {
      throw ApiError.desdeRespuesta(r.statusCode, _decodificar(r));
    }
    final j = _decodificar(r) as Map<String, dynamic>;
    _token = j['access_token'] as String;
    return j;
  }

  /// Logout: revoca la sesión en el servidor y olvida el token.
  Future<void> salir() async {
    try {
      await _enviar('POST', '/auth/sesion/logout', autenticada: false);
    } on ApiError {
      // La sesión local se cierra igual.
    }
    _token = null;
  }

  /// Sube un archivo como multipart/form-data, con [campos] de texto al lado
  /// (la foto de un plato; el certificado digital con sus claves).
  Future<dynamic> subirArchivo(
    String ruta, {
    required String campo,
    required List<int> bytes,
    required String nombreArchivo,
    Map<String, String> campos = const {},
  }) async {
    Future<http.BaseRequest> armar() async =>
        http.MultipartRequest('POST', _uri(ruta, const {}))
          ..fields.addAll(campos)
          ..files.add(
            http.MultipartFile.fromBytes(campo, bytes, filename: nombreArchivo),
          );
    final r = await _conRenovacion(armar);
    return _resultado(r);
  }

  /// Baja un archivo binario autenticado (no se abre la URL en otra pestaña:
  /// esa pestaña no tendría el token).
  Future<Descarga> descargar(
    String ruta, {
    Map<String, Object?> query = const {},
    String nombrePorDefecto = 'archivo',
  }) async {
    final r = await _conRenovacion(
      () async => _request('GET', ruta, query: query),
    );
    if (r.statusCode >= 400) {
      throw ApiError.desdeRespuesta(r.statusCode, _decodificar(r));
    }
    final cd = r.headers['content-disposition'] ?? '';
    final m = RegExp(r'filename="?([^";]+)"?').firstMatch(cd);
    return Descarga(
      r.bodyBytes,
      m?.group(1) ?? nombrePorDefecto,
      r.headers['content-type'] ?? 'application/octet-stream',
    );
  }

  /// Renueva el access token con la cookie de refresh. Serializada: si ya hay
  /// una renovación en curso, se espera a esa. Devuelve la identidad o null.
  Future<Map<String, dynamic>?> renovar() =>
      _renovacion ??= _renovarUnaVez().whenComplete(() => _renovacion = null);

  Future<Map<String, dynamic>?> _renovarUnaVez() async {
    try {
      final r = await _enviar(
        'POST',
        '/auth/sesion/refresh',
        autenticada: false,
      );
      if (r.statusCode != 200) return null;
      final j = _decodificar(r) as Map<String, dynamic>;
      _token = j['access_token'] as String;
      final usuario = j['usuario'] as Map<String, dynamic>;
      alRenovar?.call(usuario);
      return usuario;
    } on ApiError {
      return null;
    }
  }

  // ------------------------------------------------------------ interno ---

  Future<dynamic> _json(
    String metodo,
    String ruta, {
    Map<String, Object?> query = const {},
    Object? cuerpo,
  }) async {
    final r = await _conRenovacion(
      () async => _request(metodo, ruta, query: query, cuerpo: cuerpo),
    );
    return _resultado(r);
  }

  dynamic _resultado(http.Response r) {
    if (r.statusCode >= 400) {
      throw ApiError.desdeRespuesta(r.statusCode, _decodificar(r));
    }
    return _decodificar(r);
  }

  /// Envía; si responde 401 con un token puesto, renueva UNA vez y repite.
  Future<http.Response> _conRenovacion(
    Future<http.BaseRequest> Function() armar,
  ) async {
    final usado = _token;
    var r = await _mandar(await armar(), autenticada: true);
    if (r.statusCode == 401 && usado != null) {
      // Si otra petición ya renovó mientras esta viajaba, alcanza con repetir.
      final renovada =
          (_token != null && _token != usado) || await renovar() != null;
      if (!renovada) {
        _token = null;
        alCaducarSesion?.call();
        throw const ApiError.sesionCaducada();
      }
      r = await _mandar(await armar(), autenticada: true);
    }
    return r;
  }

  Future<http.Response> _enviar(
    String metodo,
    String ruta, {
    Object? cuerpo,
    bool autenticada = true,
    Map<String, String> extra = const {},
  }) => _mandar(
    _request(metodo, ruta, cuerpo: cuerpo)..headers.addAll(extra),
    autenticada: autenticada,
  );

  http.Request _request(
    String metodo,
    String ruta, {
    Map<String, Object?> query = const {},
    Object? cuerpo,
  }) {
    final req = http.Request(metodo, _uri(ruta, query));
    if (cuerpo != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(cuerpo);
    }
    return req;
  }

  Future<http.Response> _mandar(
    http.BaseRequest req, {
    required bool autenticada,
  }) async {
    req.headers['Accept'] = 'application/json';
    // Minutos a sumar a la hora local para obtener UTC (Perú = 300). El backend
    // lo usa para saber a qué día del restaurante pertenece una venta.
    req.headers['X-TZ-Offset'] = '${-DateTime.now().timeZoneOffset.inMinutes}';
    if (autenticada && _token != null) {
      req.headers['Authorization'] = 'Bearer $_token';
    }
    try {
      return await http.Response.fromStream(await _http.send(req));
    } catch (_) {
      throw const ApiError.red();
    }
  }

  Uri _uri(String ruta, Map<String, Object?> query) {
    final q = {
      for (final e in query.entries)
        if (e.value != null) e.key: '${e.value}',
    };
    return Uri.parse(
      '$base/api$ruta',
    ).replace(queryParameters: q.isEmpty ? null : q);
  }

  static Object? _decodificar(http.Response r) {
    if (r.bodyBytes.isEmpty) return null;
    try {
      return jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      return null; // Cuerpo no JSON (un proxy): se conserva solo el estado.
    }
  }
}
