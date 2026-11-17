import 'package:flutter/material.dart';

import '../../core/formato.dart';
import '../../design/tema.dart';
import 'formato_dinero.dart';
import 'modelos.dart';

/// "Ganancias por día": el número exacto de cada día, para cuadrar contra la
/// caja. El gráfico da la tendencia; esto da la cifra.
class TablaDiaria extends StatelessWidget {
  const TablaDiaria({super.key, required this.serie});

  final List<DiaSerie> serie;

  /// A este ancho o menos se ocultan Gastos y Margen: Fecha, Ventas y
  /// Ganancia es lo que se lee de un vistazo en un celular.
  static const anchoMovil = 480.0;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final completa = MediaQuery.sizeOf(context).width > anchoMovil;
    final encabezado = TextStyle(
      fontSize: 11,
      fontWeight: FontWeight.w700,
      letterSpacing: .4,
      color: c.textoSuave,
    );
    final cifra = TextStyle(
      fontSize: 13,
      color: c.textoSuave,
      fontFeatures: cifras,
    );

    TableRow fila(DiaSerie d) {
      final ganancia = d.ganancia;
      final (fondo, colorGanancia) = ganancia > 0
          ? (c.exitoFondo, c.exito)
          : ganancia < 0
          ? (c.peligroFondo, c.peligro)
          : (null, c.textoSuave);
      final margen = d.margen;
      return TableRow(
        decoration: BoxDecoration(
          color: fondo,
          border: Border(bottom: BorderSide(color: c.borde)),
        ),
        children: [
          _Celda(
            fechaTabla(d.fecha),
            estilo: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            izquierda: true,
          ),
          _Celda(soles(d.ventas), estilo: cifra),
          if (completa) _Celda(soles(d.gastos), estilo: cifra),
          _Celda(
            soles(ganancia),
            estilo: cifra.copyWith(
              color: colorGanancia,
              fontWeight: FontWeight.w700,
            ),
          ),
          if (completa)
            _Celda(
              margen == null ? '—' : '${margen.toStringAsFixed(0)}%',
              estilo: cifra,
            ),
        ],
      );
    }

    return LayoutBuilder(
      builder: (context, restr) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: ConstrainedBox(
          constraints: BoxConstraints(minWidth: restr.maxWidth),
          child: Table(
            defaultColumnWidth: const IntrinsicColumnWidth(flex: 1),
            children: [
              TableRow(
                decoration: BoxDecoration(
                  border: Border(bottom: BorderSide(color: c.borde)),
                ),
                children: [
                  _Celda('Fecha', estilo: encabezado, izquierda: true),
                  _Celda('Ventas', estilo: encabezado),
                  if (completa) _Celda('Gastos', estilo: encabezado),
                  _Celda('Ganancia', estilo: encabezado),
                  if (completa) _Celda('Margen', estilo: encabezado),
                ],
              ),
              // El backend manda la serie de la más antigua a la más reciente;
              // acá va al revés, porque lo que se busca primero es hoy.
              for (final d in serie.reversed) fila(d),
            ],
          ),
        ),
      ),
    );
  }
}

class _Celda extends StatelessWidget {
  const _Celda(this.texto, {required this.estilo, this.izquierda = false});

  final String texto;
  final TextStyle estilo;
  final bool izquierda;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
    child: Text(
      texto,
      softWrap: false,
      textAlign: izquierda ? TextAlign.left : TextAlign.right,
      style: estilo,
    ),
  );
}
