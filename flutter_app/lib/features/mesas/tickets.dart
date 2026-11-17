/// Los papeles que se imprimen desde la sala, como HTML autocontenido (estilo
/// en línea, sin scripts ni recursos externos: la CSP no los permite). Mismo
/// formato que frontend/js/print.js, pensado para la térmica de 80 mm.
library;

import '../../core/formato.dart';
import '../../core/sesion.dart';
import '../../impresion/papel.dart';
import 'modelos.dart';

/// Lo que se imprime de un pedido: una comanda o la cuenta entera de una mesa.
class PapelPedido {
  PapelPedido(List<Comanda> comandas)
    : ids = [for (final c in comandas) c.id],
      numeroMesa = comandas.first.numeroMesa,
      paraLlevar = comandas.first.paraLlevar,
      creadoEn = comandas.first.creadoEn,
      lineas = [for (final c in comandas) ...c.lineas],
      total = comandas.fold<double>(0, (s, c) => s + c.total);

  final List<int> ids;
  final int numeroMesa;
  final bool paraLlevar;
  final DateTime? creadoEn;
  final List<LineaComanda> lineas;
  final double total;

  String get numeros => ids.join(', ');

  /// numero_mesa vale 0 para llevar: "MESA: 0" mandaría a buscar una mesa
  /// que no existe. Para llevar se identifica por el número que se canta.
  String get rotulo =>
      numeroMesa > 0 ? 'MESA: $numeroMesa' : 'PARA LLEVAR N° $numeros';
}

/// El papel del comensal al pedir. Con comprobante electrónico es la
/// pre-cuenta (la boleta llega al cobrar); sin él, la pre-venta que el
/// comensal lleva a caja.
String htmlPapelCliente(PapelPedido p, Usuario u) =>
    u.usarSunat ? htmlPrecuenta(p, u) : htmlPreventa(p, u);

/// Pre-cuenta: NO FISCAL, con RUC / razón social / dirección en blanco para
/// que el cliente los complete si va a pedir el comprobante con sus datos.
String htmlPrecuenta(PapelPedido p, Usuario u) {
  final filas = p.lineas
      .map(
        (l) =>
            '<tr><td>${html(l.nombre)}</td><td class="num">${l.cantidad}</td>'
            '<td class="num">${importe(l.precioUnitario)}</td>'
            '<td class="num">${importe(l.subtotal)}</td></tr>',
      )
      .join();
  return documentoHtml(
    '.llenar { margin-top: 14px; font-size: 11px; } '
        '.llenar div { margin: 10px 0 0; border-bottom: 1px dotted #000; } '
        '.gracias { margin-top: 14px; }',
    '''
<div class="centro negocio">
  ${lineaHtml(u.razonSocial)}
  <div class="comercial">${html(u.clienteNombre)}</div>
  ${lineaHtml(u.direccion)}
  ${lineaHtml(u.clienteRuc, 'RUC: ')}
  ${lineaHtml(u.clienteEmail, 'Email: ')}
  <div>Comanda N° ${html(p.numeros)}</div>
  <div><strong>PRE-CUENTA</strong></div>
  <div>NO FISCAL</div>
</div>
<div class="campos">
  <div>MOZO: ${html(u.nombre.isEmpty ? '-' : u.nombre)}</div>
  <div>${html(p.rotulo)}</div>
  <div>CLIENTE: Publico General</div>
  <div>DOC: -</div>
</div>
<div class="linea"></div>
<div class="centro">${fechaHora(p.creadoEn)}</div>
<div class="linea"></div>
<table>
  <thead><tr><th>Articulo</th><th class="num">Cant</th><th class="num">P.U.</th><th class="num">Importe</th></tr></thead>
  <tbody>$filas</tbody>
</table>
<div class="totales">
  <div><span>Total Consumo:</span><span>${soles(p.total)}</span></div>
  <div class="total"><span>Total a pagar:</span><span>${soles(p.total)}</span></div>
</div>
<div class="llenar"><div>RUC:</div><div>RAZON SOCIAL:</div><div>DIRECCION:</div></div>
<div class="centro gracias">GRACIAS</div>
''',
  );
}

/// Pre-venta: el único papel del modo sin comprobante. El comensal la lleva a
/// caja y el cajero cobra contra ella, así que el TOTAL va grande y en su
/// recuadro. En ninguna parte se parece a una boleta: entregar algo con
/// aspecto de comprobante sin serlo sale mucho más caro que imprimir de más.
/// La razón social no va: en un RUC 10 es el nombre de una persona.
String htmlPreventa(PapelPedido p, Usuario u) {
  // Para llevar ya está pagado: "TOTAL A PAGAR" y "ENTREGUE EN CAJA" mandarían
  // a pagar dos veces lo mismo.
  final llevar = p.paraLlevar;
  final filas = p.lineas
      .map(
        (l) =>
            '<tr><td>${html(l.nombre)}</td><td class="num">${l.cantidad}</td>'
            '<td class="num">${importe(l.subtotal)}</td></tr>',
      )
      .join();
  return documentoHtml(
    '''
.negocio .comercial { font-size: 14px; }
.tipo { margin-top: 6px; font-weight: 700; letter-spacing: 1px; }
.aviso { font-size: 10px; }
.par { display: flex; justify-content: space-between; font-size: 11.5px; }
.total-caja { margin-top: 10px; border: 3px solid #000; padding: 8px 6px 10px; text-align: center; }
.total-caja .rotulo { font-size: 11px; font-weight: 700; letter-spacing: 1px; }
.total-caja .monto { font-size: 30px; font-weight: 900; line-height: 1.1; margin-top: 2px; }
.instruccion { margin-top: 10px; text-align: center; font-size: 11.5px; font-weight: 700; border: 1px dashed #000; padding: 6px 4px; }
.pie { margin-top: 12px; text-align: center; font-size: 10px; }
''',
    '''
<div class="centro negocio">
  <div class="comercial">${html(u.clienteNombre)}</div>
  ${lineaHtml(u.clienteRuc, 'RUC: ')}
  <div class="tipo">${llevar ? 'PARA LLEVAR' : 'PRE-VENTA'}</div>
  <div class="aviso">NO ES COMPROBANTE DE PAGO</div>
</div>
<div class="linea"></div>
<div class="par"><span>${llevar ? 'PARA LLEVAR' : html(p.rotulo)}</span><span>N° ${html(p.numeros)}</span></div>
<div class="par"><span>${fechaHora(p.creadoEn)}</span><span>${html(u.nombre.isEmpty ? '-' : u.nombre)}</span></div>
<div class="linea"></div>
<table>
  <thead><tr><th>Articulo</th><th class="num">Cant</th><th class="num">Importe</th></tr></thead>
  <tbody>$filas</tbody>
</table>
<div class="total-caja">
  <div class="rotulo">${llevar ? 'TOTAL PAGADO' : 'TOTAL A PAGAR'}</div>
  <div class="monto">${soles(p.total)}</div>
</div>
<div class="instruccion">${llevar ? 'SU PEDIDO: N° ${html(p.numeros)}' : 'ENTREGUE ESTA HOJA EN CAJA'}</div>
<div class="pie">GRACIAS POR SU PREFERENCIA</div>
''',
  );
}
