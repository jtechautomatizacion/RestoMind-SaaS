import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/formato.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import '../../../impresion/comprobante.dart';
import 'modelos.dart';
import 'activacion_sunat.dart';
import 'repo.dart';

/// Admin > Boletas: el interruptor de facturación electrónica y el punto de
/// recuperación de los comprobantes que no llegaron a emitirse.
///
/// El interruptor y la lista se cargan por separado: si una falla, la otra
/// igual se muestra.
class BoletasSeccion extends StatefulWidget {
  const BoletasSeccion({super.key});

  @override
  State<BoletasSeccion> createState() => _BoletasSeccionState();
}

class _BoletasSeccionState extends State<BoletasSeccion> {
  late final _repo = BoletasRepo(Servicios.leer(context).api);

  Configuracion? _cfg;
  ApiError? _errorCfg;
  Pendientes? _pendientes;
  ApiError? _errorPendientes;
  bool _cambiando = false;

  /// Filas con una emisión en curso: dos toques seguidos no deben mandar dos
  /// pedidos a SUNAT.
  final Set<String> _ocupadas = {};

  @override
  void initState() {
    super.initState();
    unawaited(_recargar());
  }

  Future<void> _recargar() =>
      Future.wait([_cargarConfiguracion(), _cargarPendientes()]);

  Future<void> _cargarConfiguracion() async {
    try {
      final cfg = await _repo.configuracion();
      if (mounted) {
        setState(() {
          _cfg = cfg;
          _errorCfg = null;
        });
      }
    } on ApiError catch (e) {
      if (mounted) {
        setState(() {
          _cfg = null;
          _errorCfg = e;
        });
      }
    }
  }

  Future<void> _cargarPendientes() async {
    try {
      final p = await _repo.pendientes();
      if (mounted) {
        setState(() {
          _pendientes = p;
          _errorPendientes = null;
        });
      }
    } on ApiError catch (e) {
      if (mounted) setState(() => _errorPendientes = e);
    }
  }

  Future<void> _cambiarFacturacion(bool activar) async {
    final cfg = _cfg!;
    // Primera vez: no es un PATCH, hace falta el certificado y la clave SOL.
    // Si ya se cargaron (se apagó y se vuelve a prender), alcanza el PATCH.
    if (activar && !cfg.datosFiscalesBloqueados) {
      final sesion = Servicios.leer(context).sesion;
      final nueva = await mostrarActivacionSunat(
        context,
        actual: cfg,
        repo: _repo,
      );
      if (nueva == null || !mounted) return;
      setState(() => _cfg = nueva);
      avisar(
        context,
        'Listo: ya puede emitir comprobantes electrónicos',
        tipo: TipoAviso.exito,
      );
      await sesion.recargarIdentidad();
      await _cargarPendientes();
      return;
    }
    if (activar &&
        !await confirmar(
          context,
          titulo: 'Activar boletas electrónicas',
          mensaje:
              'Desde ahora cada cobro emitirá un comprobante a SUNAT. '
              'Actívelo solo si el certificado digital y la clave SOL del '
              'restaurante ya están cargados.',
          accion: 'Activar',
        )) {
      return;
    }
    if (!mounted) return;
    final sesion = Servicios.leer(context).sesion;
    setState(() => _cambiando = true);
    try {
      final nueva = await _repo.cambiarFacturacion(activa: activar);
      if (!mounted) return;
      setState(() => _cfg = nueva);
      avisar(
        context,
        nueva.usarSunat ? 'Boletas activadas' : 'Boletas desactivadas',
        tipo: TipoAviso.exito,
      );
      // La identidad lleva cliente_usar_sunat, y es lo que mira Mesas al
      // cobrar para decidir si emite y si pide DNI/RUC. Sin releerla, el
      // cambio no se notaría hasta el próximo login.
      await sesion.recargarIdentidad();
      await _cargarPendientes();
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _cambiando = false);
    }
  }

  Future<void> _imprimir(Factura c, {bool contingencia = false}) {
    final s = Servicios.leer(context);
    return s.plataforma.imprimirHtml(
      htmlComprobante(
        c,
        cajero: s.sesion.usuario?.nombre ?? '-',
        contingencia: contingencia,
      ),
    );
  }

  Future<void> _emitirFila(
    String clave,
    Future<Factura> Function() emitir,
  ) async {
    setState(() => _ocupadas.add(clave));
    try {
      final c = await emitir();
      if (!mounted) return;
      avisar(context, 'Boleta ${c.numero} emitida', tipo: TipoAviso.exito);
      await _imprimir(c);
    } on ApiError catch (e) {
      if (!mounted) return;
      // El comensal ya se fue, pero el restaurante necesita el papel para su
      // control mientras regulariza: si el error trae la Factura guardada, se
      // imprime como contingencia.
      final guardado = comprobanteDelError(e);
      if (guardado != null) {
        await _imprimir(guardado, contingencia: true);
        if (mounted) {
          avisar(
            context,
            'Sigue pendiente (${e.mensaje}). Se imprimió el comprobante de '
            'contingencia.',
          );
        }
      } else {
        avisar(context, e);
      }
      // Otro aparato pudo apagar la facturación: se relee la identidad para
      // que el resto de la app deje de ofrecer comprobantes.
      if (e.codigo == 'FACTURACION_DESACTIVADA' && mounted) {
        await Servicios.leer(context).sesion.recargarIdentidad();
      }
    } finally {
      if (mounted) setState(() => _ocupadas.remove(clave));
      await _recargar();
    }
  }

  @override
  Widget build(BuildContext context) => RefreshIndicator(
    onRefresh: _recargar,
    child: ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Contenido(
          ancho: 760,
          padding: EdgeInsets.zero,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Encabezado(
                titulo: 'Boletas',
                subtitulo: 'Comprobantes electrónicos SUNAT.',
                accion: IconButton(
                  tooltip: 'Actualizar',
                  onPressed: _recargar,
                  icon: const Icon(Icons.refresh),
                ),
              ),
              _InterruptorFacturacion(
                cfg: _cfg,
                error: _errorCfg,
                cambiando: _cambiando,
                alCambiar: _cambiarFacturacion,
              ),
              ..._lista(),
            ],
          ),
        ),
      ],
    ),
  );

  List<Widget> _lista() {
    final error = _errorPendientes;
    if (error != null) {
      return [ErrorCarga(error: error, reintentar: _cargarPendientes)];
    }
    final p = _pendientes;
    if (p == null) {
      return const [
        Padding(
          padding: EdgeInsets.all(32),
          child: Center(child: CircularProgressIndicator()),
        ),
      ];
    }
    if (p.vacio) {
      return [
        Vacio(
          icono: Icons.task_alt,
          titulo: _cfg?.usarSunat == false
              ? 'Sin boletas pendientes'
              : 'Todo emitido',
          mensaje: _cfg?.usarSunat == false
              ? 'Con la facturación apagada se cobra sin comprobante.'
              : 'Todas las ventas cobradas tienen su boleta emitida.',
        ),
      ];
    }
    return [
      if (p.conError.isNotEmpty) ...[
        TituloSeccion('Boletas con error (${p.conError.length})'),
        for (final f in p.conError)
          _FilaPendiente(
            titulo: f.numeroBoleta,
            detalle:
                'Mesa ${f.numeroMesa} · ${soles(f.total)} · '
                '${fechaHora(f.creadoEn)}',
            nota: f.errorMensaje ?? 'Sin detalle del error',
            accion: 'Reintentar',
            ocupada: _ocupadas.contains('f${f.id}'),
            alPulsar: () =>
                _emitirFila('f${f.id}', () => _repo.reintentar(f.id)),
          ),
      ],
      if (p.sinBoleta.isNotEmpty) ...[
        TituloSeccion('Ventas sin boleta (${p.sinBoleta.length})'),
        for (final v in p.sinBoleta)
          _FilaPendiente(
            titulo: 'Mesa ${v.numeroMesa}',
            detalle: '${soles(v.total)} · ${fechaHora(v.creadoEn)}',
            nota: 'Cobrada, nunca se emitió boleta',
            accion: 'Emitir',
            ocupada: _ocupadas.contains('v${v.comandaIds.join(',')}'),
            alPulsar: () => _emitirFila(
              'v${v.comandaIds.join(',')}',
              () => _repo.emitir(v.comandaIds),
            ),
          ),
      ],
    ];
  }
}

class _InterruptorFacturacion extends StatelessWidget {
  const _InterruptorFacturacion({
    required this.cfg,
    required this.error,
    required this.cambiando,
    required this.alCambiar,
  });

  final Configuracion? cfg;
  final ApiError? error;
  final bool cambiando;
  final ValueChanged<bool> alCambiar;

  /// Sin respuesta del servidor el interruptor queda deshabilitado y lo dice:
  /// mostrarlo "apagado" sería afirmar que el restaurante no emite, sin haber
  /// podido consultarlo.
  String get _explicacion {
    final c = cfg;
    if (c == null) {
      return error == null
          ? 'Consultando…'
          : 'No se pudo leer la configuración. Revise la conexión y '
                'actualice.';
    }
    if (c.usarSunat) {
      return 'Emitiendo con RUC ${c.ruc ?? ''} · ${c.razonSocial ?? ''}'.trim();
    }
    if (!c.datosFiscalesBloqueados) {
      return 'Actívelo para vincular su certificado digital y empezar a emitir.';
    }
    return 'Apagado: cobra normal, sin emitir comprobantes ni pedir documento.';
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        child: Row(
          children: [
            Icon(Icons.receipt_long_outlined, color: c.textoSuave),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Emitir boletas electrónicas',
                    style: TextStyle(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    _explicacion,
                    style: TextStyle(color: c.textoSuave, fontSize: 13),
                  ),
                  if (cfg?.esAmbienteBeta == true)
                    const Padding(
                      padding: EdgeInsets.only(top: 6),
                      child: Pastilla(
                        'Ambiente de pruebas: nada tiene efecto tributario',
                        tipo: TipoEstado.aviso,
                      ),
                    ),
                ],
              ),
            ),
            Switch(
              key: const ValueKey('switch-facturacion'),
              value: cfg?.usarSunat ?? false,
              onChanged: cfg == null || cambiando ? null : alCambiar,
            ),
          ],
        ),
      ),
    );
  }
}

class _FilaPendiente extends StatelessWidget {
  const _FilaPendiente({
    required this.titulo,
    required this.detalle,
    required this.nota,
    required this.accion,
    required this.ocupada,
    required this.alPulsar,
  });

  final String titulo;
  final String detalle;
  final String nota;
  final String accion;
  final bool ocupada;
  final VoidCallback alPulsar;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      titulo,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(detalle, style: const TextStyle(fontFeatures: cifras)),
                    const SizedBox(height: 2),
                    Text(
                      nota,
                      style: TextStyle(color: c.textoSuave, fontSize: 13),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: ocupada ? null : alPulsar,
                child: Text(ocupada ? 'Emitiendo…' : accion),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
