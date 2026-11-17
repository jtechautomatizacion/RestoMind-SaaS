import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../design/tema.dart';
import 'formato_dinero.dart';
import 'modelos.dart';

/// Ventas contra gastos por día, dibujado a mano: sin librería de gráficos,
/// igual que la versión web, para no sumar peso a la app.
class GraficoVentasGastos extends StatelessWidget {
  const GraficoVentasGastos({super.key, required this.serie});

  final List<DiaSerie> serie;

  /// Ancho por día. Con 30 días el gráfico se desplaza de costado en vez de
  /// apretar las barras hasta que no se lean.
  static const anchoPorDia = 48.0;
  static const alto = 230.0;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        LayoutBuilder(
          builder: (context, restr) {
            final ancho = math.max(restr.maxWidth, serie.length * anchoPorDia);
            return SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              // Lo más reciente queda a la derecha: se abre mostrando hoy.
              reverse: true,
              child: Semantics(
                label: 'Ventas y gastos por día',
                child: CustomPaint(
                  size: Size(ancho, alto),
                  painter: PintorBarras(
                    serie: serie,
                    colorVentas: c.dinero,
                    colorGastos: c.peligro,
                    colorTexto: c.textoSuave,
                  ),
                ),
              ),
            );
          },
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 16,
          children: [
            _Leyenda(color: c.dinero, texto: 'Ventas'),
            _Leyenda(color: c.peligro, texto: 'Gastos'),
          ],
        ),
      ],
    );
  }
}

class _Leyenda extends StatelessWidget {
  const _Leyenda({required this.color, required this.texto});

  final Color color;
  final String texto;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
      const SizedBox(width: 6),
      Text(
        texto,
        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
      ),
    ],
  );
}

class PintorBarras extends CustomPainter {
  PintorBarras({
    required this.serie,
    required this.colorVentas,
    required this.colorGastos,
    required this.colorTexto,
  });

  final List<DiaSerie> serie;
  final Color colorVentas;
  final Color colorGastos;
  final Color colorTexto;

  static const _anchoBarra = 13.0;
  static const _separacion = 3.0;

  /// Lugar arriba para la etiqueta de la barra más alta, y abajo para el día.
  static const _reservaArriba = 46.0;
  static const _reservaAbajo = 24.0;

  @override
  void paint(Canvas canvas, Size size) {
    if (serie.isEmpty) return;
    final mayor = serie.fold<double>(
      0,
      (m, d) => math.max(m, math.max(d.ventas, d.gastos)),
    );
    final escala = mayor > 0 ? mayor : 1.0;
    final base = size.height - _reservaAbajo;
    final altoUtil = base - _reservaArriba;
    final paso = size.width / serie.length;

    for (final (i, d) in serie.indexed) {
      final centro = paso * i + paso / 2;
      _barra(
        canvas,
        izquierda: centro - _separacion / 2 - _anchoBarra,
        base: base,
        alto: d.ventas / escala * altoUtil,
        monto: d.ventas,
        color: colorVentas,
      );
      _barra(
        canvas,
        izquierda: centro + _separacion / 2,
        base: base,
        alto: d.gastos / escala * altoUtil,
        monto: d.gastos,
        color: colorGastos,
      );
      final dia = _texto(diaCorto(d.fecha), colorTexto, 10, FontWeight.w600);
      dia
        ..paint(
          canvas,
          Offset(centro - dia.width / 2, size.height - dia.height),
        )
        ..dispose();
    }
  }

  void _barra(
    Canvas canvas, {
    required double izquierda,
    required double base,
    required double alto,
    required double monto,
    required Color color,
  }) {
    if (monto <= 0) return;
    canvas.drawRRect(
      RRect.fromRectAndCorners(
        Rect.fromLTWH(izquierda, base - alto, _anchoBarra, alto),
        topLeft: const Radius.circular(2),
        topRight: const Radius.circular(2),
      ),
      Paint()..color = color,
    );
    // Vertical, pegada a su barra: dos números horizontales lado a lado no
    // entran en el ancho de un día y se pisarían entre sí.
    final etiqueta = _texto(compacto(monto), color, 10, FontWeight.w700);
    canvas
      ..save()
      ..translate(
        izquierda + _anchoBarra / 2 - etiqueta.height / 2,
        base - alto - 3,
      )
      ..rotate(-math.pi / 2);
    etiqueta
      ..paint(canvas, Offset.zero)
      ..dispose();
    canvas.restore();
  }

  TextPainter _texto(String s, Color color, double tam, FontWeight peso) =>
      TextPainter(
        text: TextSpan(
          text: s,
          style: TextStyle(
            color: color,
            fontSize: tam,
            fontWeight: peso,
            fontFeatures: cifras,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();

  @override
  bool shouldRepaint(PintorBarras old) =>
      old.serie != serie ||
      old.colorVentas != colorVentas ||
      old.colorGastos != colorGastos ||
      old.colorTexto != colorTexto;
}
