/// Validación del documento del comprador. Es la misma regla que valida el
/// backend (schemas.py:validar_documento_comprador); se repite acá por CUÁNDO
/// corre: el comprobante se emite después de cobrar, así que sin este chequeo
/// previo un tipeo dejaría la venta cobrada con el comprobante rechazado.
library;

/// Prefijos que SUNAT usa de verdad (espejo de backend/utils/padron.py). Con
/// solo 10 y 20 se rechazaban RUC 15/16/17 perfectamente válidos.
final _prefijosRuc = RegExp(r'^(10|15|16|17|20)');
const _pesosRuc = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];

/// Dígito verificador del RUC: atrapa el número mal tipeado antes de gastar
/// una consulta o emitir a un RUC inexistente con la venta ya cobrada.
bool digitoRucValido(String ruc) {
  if (!RegExp(r'^\d{11}$').hasMatch(ruc)) return false;
  var suma = 0;
  for (var i = 0; i < 10; i++) {
    suma += int.parse(ruc[i]) * _pesosRuc[i];
  }
  var d = 11 - (suma % 11);
  if (d == 10) d = 0;
  if (d == 11) d = 1;
  return d == int.parse(ruc[10]);
}

/// null si está bien; si no, el motivo para mostrar. Vacío = Público General.
String? validarDocumentoComprador(String documento) {
  if (documento.isEmpty) return null;
  if (!RegExp(r'^\d+$').hasMatch(documento)) {
    return 'El documento debe tener solo números.';
  }
  if (documento.length == 8) return null;
  if (documento.length == 11) {
    if (!_prefijosRuc.hasMatch(documento)) {
      return 'Un RUC debe empezar en 10, 15, 16, 17 o 20.';
    }
    if (!digitoRucValido(documento)) {
      return 'Ese RUC no existe. Revise que los 11 dígitos estén bien copiados.';
    }
    return null;
  }
  return 'El documento debe tener 8 dígitos (DNI) u 11 dígitos (RUC).';
}
