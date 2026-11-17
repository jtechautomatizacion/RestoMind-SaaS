import 'package:flutter/foundation.dart';

import '../../../core/formato.dart';

/// GET/PATCH /configuracion (ConfiguracionResponse).
@immutable
class Configuracion {
  const Configuracion({
    required this.usarSunat,
    required this.tieneRuc,
    this.ruc,
    this.razonSocial,
    this.direccionFiscal,
    this.datosFiscalesBloqueados = false,
    this.esAmbienteBeta = false,
  });

  factory Configuracion.desdeJson(Map<String, dynamic> j) => Configuracion(
    usarSunat: j['usar_sunat'] == true,
    tieneRuc: j['tiene_ruc'] == true,
    ruc: j['ruc'] as String?,
    razonSocial: j['razon_social'] as String?,
    direccionFiscal: j['direccion_fiscal'] as String?,
    datosFiscalesBloqueados: j['datos_fiscales_bloqueados'] == true,
    esAmbienteBeta: j['es_ambiente_beta'] == true,
  );

  final bool usarSunat;
  final bool tieneRuc;
  final String? ruc;
  final String? razonSocial;
  final String? direccionFiscal;

  /// true cuando el certificado YA se cargó alguna vez. Distingue "volver a
  /// prender algo configurado" (alcanza un PATCH) de "configurarlo por
  /// primera vez" (hace falta el asistente con el certificado).
  final bool datosFiscalesBloqueados;

  /// Tenant de pruebas (RUC 20000000001): nada de lo que emite tiene efecto
  /// tributario.
  final bool esAmbienteBeta;
}

/// Comprobante que ya reservó su número pero no llegó a emitirse. Se
/// reintenta CONSERVANDO ese número: la serie no puede quedar con huecos.
@immutable
class FacturaConError {
  const FacturaConError({
    required this.id,
    required this.numeroBoleta,
    required this.numeroMesa,
    required this.total,
    required this.creadoEn,
    this.errorMensaje,
  });

  factory FacturaConError.desdeJson(Map<String, dynamic> j) => FacturaConError(
    id: (j['id'] as num).toInt(),
    numeroBoleta: j['numero_boleta'] as String? ?? '',
    numeroMesa: (j['numero_mesa'] as num?)?.toInt() ?? 0,
    total: aDouble(j['total']),
    errorMensaje: j['error_mensaje'] as String?,
    creadoEn: fechaLocal(j['creado_en']),
  );

  final int id;
  final String numeroBoleta;
  final int numeroMesa;
  final double total;
  final String? errorMensaje;
  final DateTime? creadoEn;
}

/// Venta cobrada que nunca llegó a tener comprobante (la petición no alcanzó
/// el servidor). Se emite de cero sobre esas comandas, que son UNA venta.
@immutable
class VentaSinBoleta {
  const VentaSinBoleta({
    required this.numeroMesa,
    required this.comandaIds,
    required this.total,
    required this.creadoEn,
  });

  factory VentaSinBoleta.desdeJson(Map<String, dynamic> j) => VentaSinBoleta(
    numeroMesa: (j['numero_mesa'] as num?)?.toInt() ?? 0,
    comandaIds: [
      for (final id in j['comanda_ids'] as List<dynamic>? ?? const [])
        (id as num).toInt(),
    ],
    total: aDouble(j['total']),
    creadoEn: fechaLocal(j['creado_en']),
  );

  final int numeroMesa;
  final List<int> comandaIds;
  final double total;
  final DateTime? creadoEn;
}

/// GET /facturas/pendientes.
@immutable
class Pendientes {
  const Pendientes({required this.conError, required this.sinBoleta});

  factory Pendientes.desdeJson(Map<String, dynamic> j) => Pendientes(
    conError: [
      for (final f in j['facturas_con_error'] as List<dynamic>? ?? const [])
        FacturaConError.desdeJson(f as Map<String, dynamic>),
    ],
    sinBoleta: [
      for (final v in j['ventas_sin_boleta'] as List<dynamic>? ?? const [])
        VentaSinBoleta.desdeJson(v as Map<String, dynamic>),
    ],
  );

  final List<FacturaConError> conError;
  final List<VentaSinBoleta> sinBoleta;

  bool get vacio => conError.isEmpty && sinBoleta.isEmpty;
}
