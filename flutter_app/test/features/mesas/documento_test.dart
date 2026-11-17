import 'package:flutter_test/flutter_test.dart';
import 'package:restomind/features/mesas/documento.dart';

void main() {
  test('el dígito verificador acepta un RUC real y rechaza un tipeo', () {
    expect(digitoRucValido('20000000001'), isTrue);
    expect(digitoRucValido('20000000002'), isFalse);
    expect(digitoRucValido('2000000000'), isFalse);
  });

  test('vacío, DNI y RUC válido pasan; lo demás explica por qué no', () {
    expect(validarDocumentoComprador(''), isNull);
    expect(validarDocumentoComprador('73081441'), isNull);
    expect(validarDocumentoComprador('20000000001'), isNull);
    expect(validarDocumentoComprador('12345'), contains('8 dígitos'));
    expect(validarDocumentoComprador('30000000001'), contains('empezar en'));
    expect(validarDocumentoComprador('7308144a'), contains('solo números'));
  });
}
