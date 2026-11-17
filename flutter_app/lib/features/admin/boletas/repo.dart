import '../../../core/api/api_client.dart';
import '../../../core/api/api_error.dart';
import '../../../impresion/comprobante.dart';
import 'modelos.dart';

/// Facturación electrónica desde Admin > Boletas.
class BoletasRepo {
  const BoletasRepo(this._api);

  final ApiClient _api;

  Future<Configuracion> configuracion() async => Configuracion.desdeJson(
    await _api.get('/configuracion') as Map<String, dynamic>,
  );

  /// El backend rechaza prenderlo sin RUC (400): sin RUC no hay comprobante
  /// posible.
  Future<Configuracion> cambiarFacturacion({required bool activa}) async =>
      Configuracion.desdeJson(
        await _api.patch('/configuracion', {'usar_sunat': activa})
            as Map<String, dynamic>,
      );

  /// Busca el RUC del restaurante en el padrón local. Un 503 (padrón no
  /// instalado) se trata igual que "no encontrado": la razón social se
  /// escribe a mano, porque el padrón es una comodidad, no un requisito.
  Future<String?> razonSocialDelPadron(String ruc) async {
    try {
      final j = await _api.get('/documento/$ruc') as Map<String, dynamic>;
      return j['encontrado'] == true ? j['nombre'] as String? : null;
    } on ApiError catch (e) {
      if (e.status == 503 || e.status == 404) return null;
      rethrow;
    }
  }

  /// Activa la facturación en UN paso: datos fiscales, certificado .pfx con su
  /// clave y credenciales SOL. O entra todo o no se activa nada: con algo a
  /// medias cada cobro fallaría con SIN_CREDENCIALES_SOL.
  Future<Configuracion> activarConCertificado({
    required String ruc,
    required String razonSocial,
    required String direccionFiscal,
    required List<int> certificado,
    required String nombreCertificado,
    required String claveCertificado,
    required String solUsuario,
    required String solClave,
  }) async => Configuracion.desdeJson(
    await _api.subirArchivo(
          '/configuracion/subir-certificado',
          campo: 'file',
          bytes: certificado,
          nombreArchivo: nombreCertificado,
          campos: {
            'ruc': ruc,
            'password': claveCertificado,
            'sol_usuario': solUsuario,
            'sol_clave': solClave,
            'direccion_fiscal': direccionFiscal,
            // El backend la usa solo si el padrón no resolvió el RUC.
            'razon_social_manual': razonSocial,
          },
        )
        as Map<String, dynamic>,
  );

  Future<Pendientes> pendientes() async => Pendientes.desdeJson(
    await _api.get('/facturas/pendientes') as Map<String, dynamic>,
  );

  /// Reintenta con el MISMO número ya reservado.
  Future<Factura> reintentar(int facturaId) async => Factura.desdeJson(
    await _api.post('/facturas/$facturaId/reintentar') as Map<String, dynamic>,
  );

  /// Emite de cero, sin documento del comprador: quien pidió boleta con su
  /// DNI o RUC ya se fue, e inventarle uno sería peor que emitirla a
  /// Público General.
  Future<Factura> emitir(List<int> comandaIds) async => Factura.desdeJson(
    await _api.post('/facturas/generar', {'comanda_ids': comandaIds})
        as Map<String, dynamic>,
  );
}

/// El 502 de reintentar/generar trae adentro la Factura que sí se guardó: con
/// ella se imprime sin volver a preguntarle al servidor.
Factura? comprobanteDelError(ApiError e) {
  final f = e.detalle?['factura'];
  return f is Map<String, dynamic> ? Factura.desdeJson(f) : null;
}
