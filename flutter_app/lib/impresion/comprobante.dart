/// El comprobante electrónico (boleta o factura): su modelo, leído de
/// FacturaResponse, y el papel que se imprime. Lo usan la sala al cobrar y
/// Admin > Boletas al reintentar o emitir: UN solo formato, para que el mismo
/// comprobante no salga distinto según desde dónde se imprima.
library;

import '../core/formato.dart';
import 'papel.dart';

int _entero(Object? v) => (v as num?)?.toInt() ?? 0;

class DetalleFactura {
  const DetalleFactura({
    required this.descripcion,
    required this.cantidad,
    required this.precioUnitario,
    required this.subtotal,
  });

  final String descripcion;
  final int cantidad;
  final double precioUnitario;
  final double subtotal;
}

/// Lo que hace falta de FacturaResponse para imprimir el comprobante.
class Factura {
  const Factura({
    required this.numero,
    required this.serie,
    required this.estado,
    required this.numeroMesa,
    required this.subtotal,
    required this.igv,
    required this.total,
    required this.rucEmisor,
    required this.razonSocialEmisor,
    required this.nombreEmisor,
    required this.tipoDocumentoComprador,
    required this.numeroDocumentoComprador,
    required this.nombreComprador,
    required this.detalles,
    this.direccionEmisor,
    this.emailEmisor,
    this.cajero,
    this.fechaEmision,
    this.horaEmision,
  });

  factory Factura.desdeJson(Map<String, dynamic> j) => Factura(
    numero: j['numero_boleta'] as String? ?? '',
    serie: j['serie'] as String? ?? '',
    estado: j['estado'] as String? ?? '',
    numeroMesa: _entero(j['numero_mesa']),
    subtotal: aDouble(j['subtotal']),
    igv: aDouble(j['igv']),
    total: aDouble(j['total']),
    rucEmisor: j['ruc_emisor'] as String? ?? '',
    razonSocialEmisor: j['razon_social_emisor'] as String? ?? '',
    nombreEmisor: j['nombre_emisor'] as String? ?? '',
    tipoDocumentoComprador: j['tipo_documento_comprador'] as String? ?? '0',
    numeroDocumentoComprador: j['numero_documento_comprador'] as String? ?? '',
    nombreComprador: j['nombre_comprador'] as String? ?? '',
    detalles: [
      for (final d
          in (j['detalles'] as List<dynamic>? ?? const [])
              .cast<Map<String, dynamic>>())
        DetalleFactura(
          descripcion: d['descripcion'] as String? ?? '',
          cantidad: _entero(d['cantidad']),
          precioUnitario: aDouble(d['precio_unitario']),
          subtotal: aDouble(d['subtotal']),
        ),
    ],
    direccionEmisor: j['direccion_emisor'] as String?,
    emailEmisor: j['email_emisor'] as String?,
    cajero: j['cajero_nombre'] as String?,
    fechaEmision: j['fecha_emision_local'] as String?,
    horaEmision: j['hora_emision_local'] as String?,
  );

  final String numero;
  final String serie;
  final String estado;
  final int numeroMesa;
  final double subtotal;
  final double igv;
  final double total;
  final String rucEmisor;
  final String razonSocialEmisor;
  final String nombreEmisor;
  final String tipoDocumentoComprador;
  final String numeroDocumentoComprador;
  final String nombreComprador;
  final List<DetalleFactura> detalles;
  final String? direccionEmisor;
  final String? emailEmisor;
  final String? cajero;
  final String? fechaEmision;
  final String? horaEmision;

  bool get esFactura => serie.startsWith('F');
}

/// El comprobante al cobrar. Fecha y hora son las CONGELADAS en la Factura,
/// no "ahora": el papel tiene que coincidir con lo que se mandó a SUNAT.
/// Con [contingencia] el pie dice la verdad sobre su estado.
String htmlComprobante(Factura f, {String? cajero, bool contingencia = false}) {
  final filas = f.detalles
      .map(
        (d) =>
            '<tr><td>${html(d.descripcion)}</td><td class="num">${d.cantidad}</td>'
            '<td class="num">${importe(d.precioUnitario)}</td>'
            '<td class="num">${importe(d.subtotal)}</td></tr>',
      )
      .join();
  final conDocumento = f.tipoDocumentoComprador != '0';
  final etiquetaDoc = f.tipoDocumentoComprador == '6' ? 'RUC' : 'DNI';
  final nombre = f.nombreComprador.trim();
  final cliente = conDocumento
      ? '<div>CLIENTE: ${html(nombre.isEmpty ? '-' : nombre)}</div>'
            '<div>$etiquetaDoc: ${html(f.numeroDocumentoComprador)}</div>'
      : '<div>CLIENTE: Publico General</div>';
  final titular = f.razonSocialEmisor != f.nombreEmisor
      ? lineaHtml(f.razonSocialEmisor)
      : '';
  final quien = f.cajero ?? cajero;
  return documentoHtml(
    '.pie { margin-top: 14px; font-size: 10.5px; text-align: center; } '
        '.pie div { margin: 2px 0; } .fuerte { font-weight: 700; }',
    '''
<div class="centro negocio">
  $titular
  <div class="comercial">${html(f.nombreEmisor)}</div>
  ${lineaHtml(f.direccionEmisor)}
  <div>RUC: ${html(f.rucEmisor)}</div>
  ${lineaHtml(f.emailEmisor, 'Email: ')}
  <div><strong>${f.esFactura ? 'FACTURA ELECTRONICA' : 'BOLETA DE VENTA ELECTRONICA'}</strong></div>
  <div>Numero: ${html(f.numero)}</div>
</div>
<div class="campos">
  <div>CAJERO: ${html(quien == null || quien.isEmpty ? '-' : quien)}</div>
  <div>MESA: ${f.numeroMesa}</div>
  $cliente
</div>
<div class="linea"></div>
<div class="centro">${html(f.fechaEmision ?? '')} ${html(f.horaEmision ?? '')}</div>
<div class="linea"></div>
<table>
  <thead><tr><th>Articulo</th><th class="num">Cant</th><th class="num">P.U.</th><th class="num">Importe</th></tr></thead>
  <tbody>$filas</tbody>
</table>
<div class="totales">
  <div><span>Sub-Total:</span><span>${soles(f.subtotal)}</span></div>
  <div><span>IGV (18%):</span><span>${soles(f.igv)}</span></div>
  <div class="total"><span>Total Venta:</span><span>${soles(f.total)}</span></div>
</div>
<div class="pie">
  ${_pieSegunEstado(f, contingencia)}
  <div>GRACIAS POR SU COMPRA Y PREFERENCIA</div>
  <div>NO SE ACEPTAN CAMBIOS NI DEVOLUCIONES</div>
</div>
''',
  );
}

/// Un comprobante RECHAZADO no existe para SUNAT: imprimirlo como "en
/// transmisión" dejaría al cliente creyendo que tiene una boleta. Ese caso
/// sale como documento interno.
String _pieSegunEstado(Factura f, bool contingencia) {
  if (!contingencia) {
    return '<div>Representación impresa del comprobante electrónico</div>';
  }
  if (f.estado == 'error') {
    return '<div class="fuerte">DOCUMENTO INTERNO - NO ES COMPROBANTE DE PAGO</div>'
        '<div>SUNAT observó el comprobante. Será corregido y reemitido.</div>'
        '<div>Consulte su comprobante con el negocio.</div>';
  }
  return '<div class="fuerte">Representación impresa de contingencia local</div>'
      '<div>Comprobante en proceso de transmisión a SUNAT</div>';
}
