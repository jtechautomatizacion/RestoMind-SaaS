import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/formato.dart';
import '../../core/servicios.dart';
import '../../design/papel.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';
import 'documento.dart';
import 'metodo_pago.dart';
import 'modelos.dart';
import 'panel_documento.dart';
import 'repo.dart';
import 'tickets.dart';

/// Lo que pasó en la hoja de la cuenta.
sealed class ResultadoCuenta {
  const ResultadoCuenta();
}

class AgregarPedido extends ResultadoCuenta {
  const AgregarPedido();
}

/// La mesa YA se cobró. El comprobante se emite después, aparte.
class MesaCobrada extends ResultadoCuenta {
  const MesaCobrada(this.cobro, this.documento, this.nombre);

  final Cobro cobro;
  final String documento;
  final String nombre;
}

/// La cuenta de una mesa ocupada: el detalle de lo consumido, con qué paga,
/// a nombre de quién va el comprobante, y cobrar. Todo en una sola hoja: una
/// ventana encima de otra obliga a cerrar dos cosas para volver a la mesa.
class HojaCuenta extends StatefulWidget {
  const HojaCuenta({super.key, required this.mesa, required this.repo});

  final Mesa mesa;
  final MesasRepo repo;

  @override
  State<HojaCuenta> createState() => _HojaCuentaState();
}

class _HojaCuentaState extends State<HojaCuenta> {
  late Future<List<Comanda>> _cuenta = widget.repo.cuentaDeMesa(
    widget.mesa.numero,
  );

  /// Vuelve a efectivo en cada mesa: lo elegido en la anterior no se arrastra.
  MetodoPago _metodo = MetodoPago.efectivo;
  bool _cobrando = false;

  /// COBRAR Y EMITIR SON DOS PASOS, a propósito: fundirlos haría que un
  /// rechazo de SUNAT tumbe un cobro cuando la plata ya cambió de mano.
  Future<void> _cobrar(String documento, String nombre, double total) async {
    // Antes de cobrar, no después: corregir un tipeo con la mesa abierta es
    // trivial; con la venta ya cobrada, no.
    final error = validarDocumentoComprador(documento);
    if (error != null) {
      avisar(context, error);
      return;
    }
    if (!await confirmar(
      context,
      titulo: 'Cobrar la mesa ${widget.mesa.numero}',
      mensaje: 'Se cobran ${soles(total)} en ${_metodo.etiqueta}.',
      accion: 'Cobrar',
    )) {
      return;
    }
    setState(() => _cobrando = true);
    try {
      final cobro = await widget.repo.cobrar(widget.mesa.id, _metodo);
      if (mounted) {
        Navigator.pop(context, MesaCobrada(cobro, documento, nombre));
      }
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _cobrando = false);
    }
  }

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Mesa ${widget.mesa.numero}',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            IconButton(
              tooltip: 'Cerrar',
              onPressed: () => Navigator.pop(context),
              icon: const Icon(Icons.close),
            ),
          ],
        ),
        FutureBuilder<List<Comanda>>(
          future: _cuenta,
          builder: (context, s) {
            if (s.hasError) {
              return ErrorCarga(
                error: s.error!,
                reintentar: () => setState(
                  () => _cuenta = widget.repo.cuentaDeMesa(widget.mesa.numero),
                ),
              );
            }
            if (!s.hasData) {
              return const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              );
            }
            return _contenido(s.data!);
          },
        ),
      ],
    ),
  );

  Widget _contenido(List<Comanda> comandas) {
    final s = Servicios.de(context);
    final usuario = s.sesion.usuario!;
    final c = Colores.de(context);
    final total = comandas.fold<double>(0, (t, x) => t + x.total);
    final hayEnCocina = comandas.any((x) => x.enCocina);
    final agregar = usuario.esSoloCobra
        ? null
        : OutlinedButton.icon(
            onPressed: () => Navigator.pop(context, const AgregarPedido()),
            icon: const Icon(Icons.add),
            label: const Text('Agregar pedido'),
          );
    if (comandas.isEmpty) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 24),
            child: Text(
              'Esta mesa no tiene pedidos activos.',
              textAlign: TextAlign.center,
              style: TextStyle(color: c.textoSuave),
            ),
          ),
          ?agregar,
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // La cuenta se ve como la pre-cuenta impresa que recibe el comensal:
        // lo que se cobra y lo que dice el papel son lo mismo.
        TiraDePapel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (final (i, comanda) in comandas.indexed) ...[
                if (i > 0) const Corte(),
                _BloqueComanda(comanda),
              ],
              const Corte(),
              Row(
                children: [
                  Text('Total a cobrar', style: impreso(tamano: 15)),
                  const Spacer(),
                  Text(
                    soles(total),
                    style: impreso(tamano: 20, peso: FontWeight.w500),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 14),
        SelectorMetodoPago(
          valor: _metodo,
          alCambiar: (m) => setState(() => _metodo = m),
        ),
        const SizedBox(height: 12),
        // No se cobra comida que el cliente no recibió: el backend lo rechaza.
        // Se dice acá, con el motivo, en vez de dejar tocar un botón que falla.
        if (hayEnCocina)
          const AvisoAmbar('Espere a que cocina entregue todo antes de cobrar.')
        else
          PanelDocumento(
            repo: widget.repo,
            total: total,
            emite: usuario.usarSunat,
            emiteFacturas: usuario.emiteFacturas,
            ocupado: _cobrando,
            alCobrar: (doc, nombre) => _cobrar(doc, nombre, total),
          ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            OutlinedButton.icon(
              onPressed: () => s.plataforma.imprimirHtml(
                htmlPapelCliente(PapelPedido(comandas), usuario),
              ),
              icon: const Icon(Icons.print_outlined),
              label: Text(
                usuario.usarSunat
                    ? 'Imprimir pre-cuenta'
                    : 'Imprimir pre-venta',
              ),
            ),
            ?agregar,
          ],
        ),
      ],
    );
  }
}

class _BloqueComanda extends StatelessWidget {
  const _BloqueComanda(this.comanda);

  final Comanda comanda;

  @override
  Widget build(BuildContext context) {
    final p = Papel.de(context);
    final (texto, icono, color) = comanda.enCocina
        ? ('En cocina', Icons.local_fire_department_outlined, p.aviso)
        : ('Entregado', Icons.check, p.exito);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(icono, size: 16, color: color),
            const SizedBox(width: 4),
            Text(
              texto,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
            const Spacer(),
            Text(soles(comanda.total), style: impreso(tamano: 14)),
          ],
        ),
        for (final l in comanda.lineas)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '${l.cantidad} x ${l.nombre}',
                    style: impreso(tamano: 14),
                  ),
                ),
                Text(soles(l.subtotal), style: impreso(tamano: 14)),
              ],
            ),
          ),
      ],
    );
  }
}
