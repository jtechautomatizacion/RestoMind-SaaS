import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/formato.dart';
import '../../core/servicios.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';
import 'grafico.dart';
import 'modelos.dart';
import 'rankings.dart';
import 'repo.dart';
import 'selector_periodo.dart';
import 'tabla_diaria.dart';

/// CU-05: "cómo viaja su dinero". Ventas contra gastos, ganancia, el detalle
/// por día y lo que más vende, para el período elegido.
class DineroPage extends StatefulWidget {
  const DineroPage({super.key});

  @override
  State<DineroPage> createState() => _DineroPageState();
}

class _DineroPageState extends State<DineroPage> {
  late final DineroRepo _repo = DineroRepo(Servicios.leer(context).api);

  Periodo _periodo = const Periodo.ultimos(7);
  bool _exportando = false;

  void _cambiarPeriodo(Periodo p) {
    if (p != _periodo) setState(() => _periodo = p);
  }

  Future<void> _exportar() async {
    final plataforma = Servicios.leer(context).plataforma;
    setState(() => _exportando = true);
    try {
      final archivo = await _repo.reporteExcel(_periodo);
      await plataforma.descargar(archivo.bytes, archivo.nombre, archivo.tipo);
      if (mounted) avisar(context, 'Reporte descargado', tipo: TipoAviso.exito);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _exportando = false);
    }
  }

  @override
  Widget build(BuildContext context) => Cargador<Resumen>(
    // Un Cargador por período: al cambiarlo se arma uno nuevo y pide los
    // datos de ese período, sin mezclar respuestas de uno y otro.
    key: ValueKey(_periodo),
    cargar: () => _repo.resumen(_periodo),
    construir: (context, resumen, _) => ListView(
      padding: EdgeInsets.zero,
      children: [
        Contenido(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Encabezado(titulo: 'Su dinero', subtitulo: _periodo.etiqueta),
              SelectorPeriodo(periodo: _periodo, alCambiar: _cambiarPeriodo),
              const SizedBox(height: 16),
              _Indicadores(totales: resumen.totales),
              _Bloque(
                titulo: 'Ventas vs Gastos',
                // Un gráfico de barras en cero no dice nada: se explica qué
                // falta para que aparezca.
                child:
                    resumen.serie.every((d) => d.ventas == 0 && d.gastos == 0)
                    ? const Vacio(
                        icono: Icons.bar_chart_outlined,
                        titulo: 'Todavía no hay movimientos en estos días',
                        mensaje:
                            'Las ventas aparecen al cobrar una mesa, y los gastos al registrarlos en Admin > Gastos.',
                      )
                    : GraficoVentasGastos(serie: resumen.serie),
              ),
              _Bloque(
                titulo: 'Ganancias por día',
                pista: 'detalle diario',
                child: resumen.serie.isEmpty
                    ? const Text('Sin datos para mostrar.')
                    : TablaDiaria(serie: resumen.serie),
              ),
              _Bloque(
                titulo: 'Top 5 platos',
                pista: 'por ingresos',
                child: TopPlatos(platos: resumen.topPlatos),
              ),
              _Bloque(
                titulo: 'Top 3 gastos',
                pista: 'por categoría',
                child: TopGastos(gastos: resumen.topGastos),
              ),
              _Bloque(
                titulo: 'Salón y mostrador',
                pista: 'dónde se vende',
                child: VentasPorTipo(
                  filas: resumen.porTipoPedido,
                  etiquetas: etiquetasTipoPedido,
                ),
              ),
              _Bloque(
                titulo: 'Efectivo y Yape',
                pista: 'dónde está la plata',
                child: VentasPorTipo(
                  filas: resumen.porMetodoPago,
                  etiquetas: etiquetasMetodoPago,
                ),
              ),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: _exportando ? null : _exportar,
                icon: const Icon(Icons.download),
                label: Text(
                  _exportando ? 'Generando...' : 'Descargar reporte Excel',
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

/// Ventas, gastos, ganancia y margen del período. Salen de los totales del
/// backend, ya redondeados a céntimos, y no de sumar la serie acá: sumar
/// decimales en punto flotante puede dejar un céntimo de diferencia.
class _Indicadores extends StatelessWidget {
  const _Indicadores({required this.totales});

  final Totales totales;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final margen = totales.margen;
    final tarjetas = [
      Indicador(
        etiqueta: 'Ventas',
        valor: soles(totales.ventas),
        color: c.dinero,
      ),
      Indicador(
        etiqueta: 'Gastos',
        valor: soles(totales.gastos),
        color: c.peligro,
      ),
      Indicador(
        etiqueta: 'Ganancia',
        valor: soles(totales.ganancia),
        color: totales.ganancia < 0 ? c.peligro : c.exito,
      ),
      Indicador(
        etiqueta: 'Margen',
        valor: margen == null ? '—' : '${margen.toStringAsFixed(0)}%',
      ),
    ];
    return LayoutBuilder(
      builder: (context, restr) {
        const separacion = 12.0;
        final columnas = restr.maxWidth >= 640 ? 4 : 2;
        final ancho = (restr.maxWidth - separacion * (columnas - 1)) / columnas;
        return Wrap(
          spacing: separacion,
          runSpacing: separacion,
          children: [
            for (final t in tarjetas) SizedBox(width: ancho, child: t),
          ],
        );
      },
    );
  }
}

class _Bloque extends StatelessWidget {
  const _Bloque({required this.titulo, required this.child, this.pista});

  final String titulo;
  final String? pista;
  final Widget child;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 16),
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    titulo,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                if (pista != null)
                  Text(
                    pista!,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colores.de(context).textoSuave,
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    ),
  );
}
