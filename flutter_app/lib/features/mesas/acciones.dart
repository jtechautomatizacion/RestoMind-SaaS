import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/formato.dart';
import '../../core/servicios.dart';
import '../../design/widgets.dart';
import 'cuenta_hoja.dart';
import '../../impresion/comprobante.dart';
import 'modelos.dart';
import 'pedido_hoja.dart';
import 'sala.dart';
import 'tickets.dart';

/// Lo que pasa al tocar una mesa, el mismo camino desde la grilla clásica y
/// desde "Atiendo solo": un solo flujo de pedido y de cobro, porque dos
/// versiones de la lógica de dinero terminan desincronizándose.
///
/// [context] es el de la PÁGINA, no el de una hoja: el comprobante se emite
/// cuando la hoja ya se cerró, y sus avisos tienen que tener dónde salir.
Future<void> abrirMesa(BuildContext context, Sala sala, Mesa mesa) async {
  if (mesa.ocupada) return abrirCuenta(context, sala, mesa);
  // Quien solo cobra nunca toma pedidos.
  if (Servicios.leer(context).sesion.usuario!.esSoloCobra) return;
  return abrirPedido(context, sala, mesa: mesa);
}

/// Nuevo pedido de [mesa], o PARA LLEVAR si es null.
Future<void> abrirPedido(BuildContext context, Sala sala, {Mesa? mesa}) async {
  final r = await mostrarHoja<(Comanda, MetodoPago)>(
    context,
    (_) => HojaPedido(repo: sala.repo, carta: sala.carta, mesa: mesa),
  );
  if (r == null || !context.mounted) return;
  final (comanda, metodo) = r;
  final s = Servicios.leer(context);
  // Para llevar se paga al pedirlo: el aviso dice que YA se cobró, si no el
  // cajero podría quedarse esperando para cobrarlo después.
  // El papel del comensal NO se imprime solo: el servidor ya encola los
  // papeles para la impresora de cada estación, y sacarlo además acá lo
  // duplicaría. Queda a un toque, en el aviso.
  avisar(
    context,
    comanda.paraLlevar
        ? 'Cobrado en ${metodo.etiqueta} y enviado a cocina'
        : 'Comanda enviada a cocina',
    tipo: TipoAviso.exito,
    accion: (
      'Imprimir',
      () => s.plataforma.imprimirHtml(
        htmlPapelCliente(PapelPedido([comanda]), s.sesion.usuario!),
      ),
    ),
  );
  await sala.refrescar();
}

/// La cuenta de una mesa ocupada: agregar otro pedido o cobrarla.
Future<void> abrirCuenta(BuildContext context, Sala sala, Mesa mesa) async {
  final r = await mostrarHoja<ResultadoCuenta>(
    context,
    (_) => HojaCuenta(mesa: mesa, repo: sala.repo),
  );
  if (!context.mounted) return;
  switch (r) {
    case null:
      return;
    case AgregarPedido():
      return abrirPedido(context, sala, mesa: mesa);
    case final MesaCobrada venta:
      final cobro = venta.cobro;
      // Dice CON QUÉ se cobró: es la única confirmación de que la plata quedó
      // en el bolsillo correcto, y un error ahí aparece recién al arquear.
      avisar(
        context,
        'Cobrado ${soles(cobro.total)} en ${cobro.metodo.etiqueta} · '
        'Mesa ${cobro.mesaNumero} libre',
        tipo: TipoAviso.exito,
      );
      unawaited(sala.refrescar());
      // Solo si el restaurante emite desde la app: se vende desde el día uno
      // y SUNAT se configura después, sin un aviso rojo en cada cobro.
      if (Servicios.leer(context).sesion.usuario!.usarSunat) {
        await emitirComprobante(context, sala, venta);
      }
  }
}

/// Emite el comprobante de una mesa YA cobrada. Pase lo que pase acá, el cobro
/// no se deshace: lo que falle queda recuperable en Admin > Boletas.
Future<void> emitirComprobante(
  BuildContext context,
  Sala sala,
  MesaCobrada venta,
) async {
  final s = Servicios.leer(context);
  final cajero = s.sesion.usuario!.nombre;
  try {
    final factura = await sala.repo.generarComprobante(
      comandaIds: venta.cobro.comandaIds,
      documento: venta.documento,
      nombre: venta.nombre,
    );
    if (!context.mounted) return;
    avisar(context, '${factura.numero} generada', tipo: TipoAviso.exito);
    // Un DNI escrito a mano se recuerda para la próxima visita. Si falla, solo
    // se pierde esa comodidad.
    if (venta.nombre.isNotEmpty && venta.documento.length == 8) {
      unawaited(
        sala.repo
            .recordarDocumento(venta.documento, venta.nombre)
            .catchError((Object _) {}),
      );
    }
    // Recién acá hay un número de comprobante real para poner en el papel.
    await s.plataforma.imprimirHtml(htmlComprobante(factura, cajero: cajero));
  } on ApiError catch (e) {
    if (!context.mounted) return;
    switch (e.codigo) {
      case 'IDENTIFICAR_COMPRADOR':
        await _avisarTope700(context, e.mensaje);
        return;
      case 'FACTURACION_DESACTIVADA':
        // El dueño apagó la facturación con esta sesión abierta. No es un
        // fallo: la venta ya está en caja. Se relee la identidad del servidor
        // para que la pantalla deje de ofrecer comprobantes.
        await s.sesion.recargarIdentidad();
        if (context.mounted) {
          avisar(
            context,
            'Venta registrada en caja. Este restaurante no emite comprobantes.',
          );
        }
        return;
    }
    // Contingencia: el backend devuelve la factura YA GUARDADA dentro del
    // error, así que se imprime sin volver a pedirle nada al servidor, que es
    // justo lo que puede estar caído. El pie dice en qué estado quedó.
    final guardada = e.detalle?['factura'];
    final impreso = guardada is Map<String, dynamic>;
    if (impreso) {
      await s.plataforma.imprimirHtml(
        htmlComprobante(
          Factura.desdeJson(guardada),
          cajero: cajero,
          contingencia: true,
        ),
      );
    }
    if (!context.mounted) return;
    final detalle = e.esRed ? 'se cortó la conexión' : e.mensaje;
    avisar(
      context,
      impreso
          ? 'Cobro registrado. Ticket impreso; el comprobante quedó pendiente '
                'en Admin > Boletas ($detalle).'
          : 'Cobro registrado, pero el comprobante NO se emitió ($detalle). '
                'Emítalo desde Admin > Boletas.',
      tipo: impreso ? TipoAviso.info : TipoAviso.error,
    );
  }
}

/// La regla de los S/ 700 va en un diálogo y no en un aviso que se va solo:
/// esto el cajero TIENE que leerlo. Lo primero que dice es que el cobro SÍ
/// entró, que es su duda inmediata con el cliente enfrente.
Future<void> _avisarTope700(BuildContext context, String mensaje) =>
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: const Icon(Icons.description_outlined),
        title: const Text('Cobro registrado'),
        content: Text(
          '$mensaje\n\nEl comprobante quedó pendiente en Admin > Boletas. '
          'Pídale el DNI o RUC al cliente y emítalo desde ahí.',
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Entendido'),
          ),
        ],
      ),
    );
