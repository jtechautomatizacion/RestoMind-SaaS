import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/formato.dart';
import '../../../core/servicios.dart';
import '../../../design/widgets.dart';
import '../../../shell/shell.dart';
import 'formularios.dart';
import 'modelos.dart';
import 'repo.dart';
import 'reporte_cierre.dart';
import 'tarjetas.dart';

typedef _DatosCaja = ({EstadoCaja estado, List<Turno>? historial});

/// Admin > Caja: abrir y cerrar turnos, con el arqueo que calcula el backend.
///
/// Dos pantallas posibles y la decide GET /caja/estado, nunca esta app:
///  · hay un turno abierto → lo vendido hasta ahora y el formulario de cierre;
///  · no hay → el último cierre de hoy (si hubo) y el formulario de apertura,
///    que siempre está disponible: un restaurante puede tener varios turnos.
class CajaSeccion extends StatefulWidget {
  const CajaSeccion({super.key});

  @override
  State<CajaSeccion> createState() => _CajaSeccionState();
}

class _CajaSeccionState extends State<CajaSeccion> {
  late final _repo = CajaRepo(Servicios.leer(context).api);

  Future<_DatosCaja> _cargar() async {
    final historial = _repo.historial().then<List<Turno>?>(
      (h) => h,
      // Sin historial la pantalla igual sirve para abrir o cerrar.
      onError: (Object _) => null,
    );
    return (estado: await _repo.estado(), historial: await historial);
  }

  /// Recarga conservando lo que ya se ve mientras llegan los datos nuevos.
  final _cargador = GlobalKey<CargadorState<_DatosCaja>>();

  void _recargar() => _cargador.currentState?.recargar();

  Future<void> _imprimir(Turno t) =>
      Servicios.leer(context).plataforma.imprimirHtml(
        reporteCierreHtml(
          t,
          negocio:
              Servicios.leer(context).sesion.usuario?.clienteNombre ??
              'Mi restaurante',
          impreso: DateTime.now(),
        ),
      );

  /// Mesas y Cocina se desbloquean (o bloquean) al toque, sin esperar a la
  /// próxima consulta del shell (hasta 20 s).
  Future<void> _refrescarGate() =>
      ShellScope.leer(context).cajaGate.refrescar();

  Future<void> _abrir(double saldoInicial, String? nombreTurno) async {
    try {
      await _repo.abrir(saldoInicial: saldoInicial, nombreTurno: nombreTurno);
      if (!mounted) return;
      avisar(context, 'Caja abierta', tipo: TipoAviso.exito);
      await _refrescarGate();
      _recargar();
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    }
  }

  Future<void> _cerrar(double contado, double retiros, String? razon) async {
    // Cerrar congela las ventas y gastos del turno: no tiene "deshacer".
    final ok = await confirmar(
      context,
      titulo: 'Cerrar caja',
      mensaje:
          'Dinero contado: ${soles(contado)}. '
          '¿Confirma el cierre? Esta acción no se puede deshacer.',
      accion: 'Cerrar caja',
      peligrosa: true,
    );
    if (!ok || !mounted) return;
    try {
      final cierre = await _repo.cerrar(
        saldoContado: contado,
        retiros: retiros,
        razon: razon,
      );
      if (!mounted) return;
      avisar(context, 'Caja cerrada', tipo: TipoAviso.exito);
      await _refrescarGate();
      _recargar();
      // El dueño quiere ver el reporte apenas cierra, no ir a buscarlo.
      if (mounted) await _imprimir(cierre);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    }
  }

  @override
  Widget build(BuildContext context) => Cargador<_DatosCaja>(
    key: _cargador,
    cargar: _cargar,
    construir: (context, datos, _) {
      final estado = datos.estado;
      final abierta = estado.hayCajaAbierta && estado.abierta != null;
      final ultimo = estado.ultimoCierreHoy;
      return ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Contenido(
            ancho: 760,
            padding: EdgeInsets.zero,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Encabezado(
                  titulo: 'Caja',
                  subtitulo: 'Apertura y cierre de cada turno.',
                  accion: IconButton(
                    tooltip: 'Actualizar',
                    onPressed: _recargar,
                    icon: const Icon(Icons.refresh),
                  ),
                ),
                if (abierta) ...[
                  TurnoAbiertoCard(estado: estado),
                  const SizedBox(height: 12),
                  FormCerrarCaja(alCerrar: _cerrar),
                ] else ...[
                  if (ultimo != null) ...[
                    UltimoCierreCard(
                      turno: ultimo,
                      turnosHoy: estado.turnosHoy,
                      alImprimir: () => _imprimir(ultimo),
                    ),
                    const SizedBox(height: 12),
                  ],
                  FormAbrirCaja(alAbrir: _abrir),
                ],
                const TituloSeccion('Historial de cierres'),
                HistorialCaja(turnos: datos.historial, alImprimir: _imprimir),
              ],
            ),
          ),
        ],
      );
    },
  );
}
