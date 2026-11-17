/// Error de una llamada a la API, ya traducido a algo que se puede mostrar.
///
/// FastAPI devuelve `detail` de tres formas y las tres se aceptan:
///  · un texto (`HTTPException(detail="...")`);
///  · una lista (validación 422 de Pydantic);
///  · un objeto con `codigo` y `mensaje` (errores de negocio con código
///    estable, p. ej. `IDENTIFICAR_COMPRADOR` o `FACTURACION_DESACTIVADA`).
///    El objeto completo queda en [detalle] para quien necesite más datos
///    (el 502 de /facturas/generar trae la factura guardada adentro).
class ApiError implements Exception {
  const ApiError({
    required this.status,
    required this.mensaje,
    this.codigo,
    this.detalle,
  });

  /// Sin respuesta del servidor (red caída, servidor apagado).
  const ApiError.red()
    : status = 0,
      mensaje = 'Sin conexión con el servidor. Revise el internet del local.',
      codigo = 'SIN_CONEXION',
      detalle = null;

  const ApiError.sesionCaducada()
    : status = 401,
      mensaje = 'Su sesión terminó. Inicie sesión de nuevo.',
      codigo = 'SESION_CADUCADA',
      detalle = null;

  final int status;
  final String mensaje;
  final String? codigo;
  final Map<String, dynamic>? detalle;

  bool get esRed => status == 0;

  factory ApiError.desdeRespuesta(int status, Object? cuerpo) {
    var mensaje = _porEstado(status);
    String? codigo;
    Map<String, dynamic>? detalle;
    if (cuerpo is Map<String, dynamic>) {
      final d = cuerpo['detail'];
      if (d is String && d.isNotEmpty) {
        mensaje = d;
      } else if (d is List && d.isNotEmpty) {
        mensaje = d
            .map((e) => e is Map ? '${e['msg'] ?? ''}' : '$e')
            .where((m) => m.isNotEmpty)
            .join('. ');
        if (mensaje.isEmpty) mensaje = _porEstado(status);
      } else if (d is Map<String, dynamic>) {
        detalle = d;
        codigo = d['codigo'] as String?;
        final m = d['mensaje'] ?? d['detail'];
        if (m is String && m.isNotEmpty) mensaje = m;
      }
    }
    return ApiError(
      status: status,
      mensaje: mensaje,
      codigo: codigo,
      detalle: detalle,
    );
  }

  static String _porEstado(int status) => switch (status) {
    400 => 'Los datos enviados no son válidos.',
    403 => 'Su cuenta no tiene permiso para esta acción.',
    404 => 'No se encontró lo que buscaba.',
    409 => 'La operación no corresponde en este momento.',
    422 => 'Revise los datos del formulario.',
    429 => 'Demasiados intentos. Espere unos minutos.',
    >= 500 => 'El servidor tuvo un problema. Intente de nuevo.',
    _ => 'La operación no se pudo completar.',
  };

  @override
  String toString() => mensaje;
}
