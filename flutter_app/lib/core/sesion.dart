import 'package:flutter/foundation.dart';

import 'api/api_client.dart';
import 'api/api_error.dart';
import 'roles.dart';

/// Quién está usando la app y de qué restaurante. Viene de /auth/login,
/// /auth/sesion/refresh o /auth/me (UsuarioMe del backend).
@immutable
class Usuario {
  const Usuario({
    required this.email,
    required this.nombre,
    required this.rol,
    required this.roles,
    required this.clienteId,
    required this.clienteNombre,
    this.clienteRuc,
    this.usarSunat = false,
    this.emiteFacturas = false,
    this.razonSocial,
    this.direccion,
    this.clienteEmail,
  });

  factory Usuario.desdeJson(Map<String, dynamic> j) => Usuario(
    email: j['email'] as String? ?? '',
    nombre: j['nombre'] as String? ?? '',
    rol: j['rol'] as String? ?? '',
    roles: [for (final r in j['roles'] as List<dynamic>? ?? const []) '$r'],
    clienteId: j['cliente_id'] as String? ?? '',
    clienteNombre: j['cliente_nombre'] as String? ?? '',
    clienteRuc: j['cliente_ruc'] as String?,
    usarSunat: j['cliente_usar_sunat'] as bool? ?? false,
    emiteFacturas: j['cliente_emite_facturas'] as bool? ?? false,
    razonSocial: j['cliente_razon_social'] as String?,
    direccion: j['cliente_direccion'] as String?,
    clienteEmail: j['cliente_email'] as String?,
  );

  final String email;
  final String nombre;
  final String rol;
  final List<String> roles;
  final String clienteId;
  final String clienteNombre;
  final String? clienteRuc;

  /// ¿Este restaurante emite comprobantes SUNAT desde la app? (Admin > Boletas)
  final bool usarSunat;

  /// ¿Puede emitir FACTURAS o solo boletas? (Nuevo RUS: solo boletas)
  final bool emiteFacturas;
  final String? razonSocial;
  final String? direccion;
  final String? clienteEmail;

  bool get esSuperadmin => rol == 'superadmin';
  bool get esAdmin => roles.contains('admin');
  bool tiene(String r) => roles.contains(r);
  List<Pestana> get pestanas => pestanasDe(roles);
  bool get vistaUnificada => veVistaUnificada(roles);
  bool get esSoloCobra => soloCobra(roles);
  String get etiquetaRoles => roles.map((r) => etiquetaRol[r] ?? r).join(' + ');
}

enum EstadoSesion { comprobando, anonima, autenticada }

/// Estado de la sesión. El access token vive en [ApiClient] (memoria).
class Sesion extends ChangeNotifier {
  Sesion(this._api) {
    _api.alCaducarSesion = caducada;
    _api.alRenovar = (u) {
      usuario = Usuario.desdeJson(u);
      notifyListeners();
    };
  }

  final ApiClient _api;

  EstadoSesion estado = EstadoSesion.comprobando;
  Usuario? usuario;

  /// Motivo de la última salida forzada, para mostrarlo en el login.
  String? avisoSalida;

  /// Al abrir la app: si la cookie de refresh sigue viva, la sesión continúa
  /// sin volver a pedir la contraseña.
  Future<void> iniciar() async {
    final u = await _api.renovar();
    if (u != null) {
      _autenticar(u);
    } else {
      estado = EstadoSesion.anonima;
      notifyListeners();
    }
  }

  /// Dueño/admin: email + contraseña. Lanza [ApiError] para que el login lo explique.
  Future<Usuario> entrarConEmail(String email, String password) async {
    final j = await _api.entrar('/auth/login', {
      'email': email,
      'password': password,
    });
    return _alEntrar(j);
  }

  /// Personal: código de acceso de 6 dígitos + contraseña.
  Future<Usuario> entrarConCodigo(String codigo, String password) async {
    final j = await _api.entrar('/auth/login-staff', {
      'celular': codigo,
      'password': password,
    });
    return _alEntrar(j);
  }

  Usuario _alEntrar(Map<String, dynamic> j) {
    final u = Usuario.desdeJson(j['usuario'] as Map<String, dynamic>);
    if (u.esSuperadmin) {
      // El panel general es otra página con su propio login: este token no se
      // guarda ni se usa acá.
      _api.fijarToken(null);
      return u;
    }
    _autenticar(j['usuario'] as Map<String, dynamic>);
    return u;
  }

  void _autenticar(Map<String, dynamic> u) {
    usuario = Usuario.desdeJson(u);
    avisoSalida = null;
    estado = EstadoSesion.autenticada;
    notifyListeners();
  }

  /// Vuelve a leer la identidad (p. ej. después de prender la facturación).
  Future<void> recargarIdentidad() async {
    try {
      final j = await _api.get('/auth/me') as Map<String, dynamic>;
      usuario = Usuario.desdeJson(j);
      notifyListeners();
    } on ApiError {
      // Si falla, se conserva la identidad anterior.
    }
  }

  Future<void> salir() async {
    await _api.salir();
    _limpiar(null);
  }

  void caducada() => _limpiar('Su sesión terminó. Inicie sesión de nuevo.');

  void contrasenaCambiada() =>
      _limpiar('Su contraseña cambió. Entre con la nueva.');

  void _limpiar(String? aviso) {
    _api.fijarToken(null);
    usuario = null;
    avisoSalida = aviso;
    estado = EstadoSesion.anonima;
    notifyListeners();
  }
}
