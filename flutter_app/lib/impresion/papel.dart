/// Base de todos los papeles que imprime la app (pre-cuenta, pre-venta,
/// comprobante): HTML autocontenido para la térmica de 80 mm. Estilo en línea,
/// sin scripts ni recursos externos, que la CSP de la app no permite.
library;

import '../core/formato.dart';

const _estiloBase = '''
@page { size: 80mm auto; margin: 4mm; }
* { box-sizing: border-box; }
body { font-family: 'Courier New', Courier, monospace; margin: 0; padding: 0; color: #000; font-size: 12px; }
.centro { text-align: center; }
.linea { border-top: 1px dashed #000; margin: 6px 0; }
.negocio div { margin: 1px 0; }
.negocio .comercial { font-weight: 700; }
.campos div { margin: 1px 0; }
table { width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 4px; }
th { text-align: left; font-size: 10.5px; border-bottom: 1px solid #000; padding-bottom: 3px; }
th.num, td.num { text-align: right; }
td { padding: 3px 0; vertical-align: top; }
.totales { margin-top: 4px; }
.totales div { display: flex; justify-content: space-between; }
.totales .total { font-weight: 900; }
''';

/// Documento completo con el estilo base más el [estilo] propio del papel.
String documentoHtml(String estilo, String cuerpo) =>
    '<!DOCTYPE html><html><head><meta charset="UTF-8"><style>$_estiloBase$estilo</style></head><body>$cuerpo</body></html>';

/// Una línea solo si hay texto (un dato vacío no deja un renglón en blanco).
String lineaHtml(String? texto, [String prefijo = '']) =>
    texto == null || texto.isEmpty ? '' : '<div>$prefijo${html(texto)}</div>';

/// Importe sin el símbolo, para las columnas del detalle.
String importe(double v) => v.toStringAsFixed(2);
