import 'package:flutter/material.dart';

import '../core/formato.dart';
import 'tema.dart';

/// El papel térmico: lo que en el local SALE IMPRESO (la comanda colgada en el
/// riel de la cocina, la pre-cuenta) se dibuja como papel claro con tinta
/// oscura y letra mono, igual que lo saca la impresora.
///
/// Es el único elemento claro de la app en el tema oscuro, y es a propósito:
/// la cocina lee la comanda de lejos, con las manos ocupadas y con poca luz,
/// y papel claro sobre pizarra oscura es lo que más contraste da.
///
/// Sobre el papel los colores con significado van en su versión OSCURA (la
/// del tema claro): un rojo pensado para fondo negro no se lee sobre blanco.
@immutable
class Papel extends ThemeExtension<Papel> {
  const Papel({
    required this.papel,
    required this.tinta,
    required this.tintaSuave,
    required this.corte,
    required this.riel,
    required this.peligro,
    required this.aviso,
    required this.exito,
  });

  /// Blanco frío de rollo térmico (no crema: el térmico no es amarillento).
  final Color papel;
  final Color tinta;
  final Color tintaSuave;

  /// Línea punteada entre secciones del papel.
  final Color corte;

  /// Fondo del riel donde se cuelgan las comandas.
  final Color riel;
  final Color peligro;
  final Color aviso;
  final Color exito;

  static const oscuro = Papel(
    papel: Color(0xFFEEF1F3),
    tinta: Color(0xFF15191D),
    tintaSuave: Color(0xFF5A636D),
    corte: Color(0xFFB9C1C9),
    riel: Color(0xFF0A0D10),
    peligro: Color(0xFFC62828),
    aviso: Color(0xFF9A5B00),
    exito: Color(0xFF15803D),
  );

  /// En el tema claro el papel es blanco puro y el riel una franja gris
  /// azulada: si no, el papel se perdería contra el fondo de la app.
  static const claro = Papel(
    papel: Color(0xFFFFFFFF),
    tinta: Color(0xFF15191D),
    tintaSuave: Color(0xFF5A636D),
    corte: Color(0xFFC3CCD6),
    riel: Color(0xFFD5DCE4),
    peligro: Color(0xFFC62828),
    aviso: Color(0xFF9A5B00),
    exito: Color(0xFF15803D),
  );

  static Papel de(BuildContext context) =>
      Theme.of(context).extension<Papel>()!;

  @override
  Papel copyWith() => this;

  @override
  Papel lerp(ThemeExtension<Papel>? other, double t) =>
      t < .5 ? this : (other as Papel? ?? this);
}

/// Texto "impreso": IBM Plex Mono, como la térmica. Solo para lo que de verdad
/// sale en el papel (número de mesa, ítems, montos, hora).
TextStyle impreso({
  double tamano = 15,
  FontWeight peso = FontWeight.w500,
  Color? color,
  double espaciado = 0,
}) => TextStyle(
  fontFamily: fuenteMono,
  fontSize: tamano,
  fontWeight: peso,
  color: color,
  letterSpacing: espaciado,
  fontFeatures: cifras,
  height: 1.3,
);

/// Una tira de papel con el borde de arriba troquelado, como la comanda recién
/// cortada de la impresora.
class TiraDePapel extends StatelessWidget {
  const TiraDePapel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.fromLTRB(16, 18, 16, 14),
    this.marca,
  });

  final Widget child;
  final EdgeInsets padding;

  /// Franja de color en el borde izquierdo (el estado de la comanda).
  final Color? marca;

  @override
  Widget build(BuildContext context) {
    final p = Papel.de(context);
    return CustomPaint(
      painter: _Troquel(p.papel),
      child: Container(
        margin: const EdgeInsets.only(top: _Troquel.alto),
        decoration: BoxDecoration(
          color: p.papel,
          borderRadius: const BorderRadius.vertical(bottom: Radius.circular(6)),
          border: marca == null
              ? null
              : Border(left: BorderSide(color: marca!, width: 5)),
          boxShadow: const [
            BoxShadow(
              color: Color(0x40000000),
              blurRadius: 10,
              offset: Offset(0, 4),
            ),
          ],
        ),
        padding: padding,
        child: DefaultTextStyle.merge(
          style: TextStyle(color: p.tinta),
          child: IconTheme.merge(
            data: IconThemeData(color: p.tinta),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// Dientes de sierra arriba: el corte de la tira.
class _Troquel extends CustomPainter {
  _Troquel(this.color);

  static const alto = 6.0;
  static const ancho = 10.0;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()..moveTo(0, alto);
    var x = 0.0;
    while (x < size.width) {
      path
        ..lineTo(x + ancho / 2, 0)
        ..lineTo((x + ancho).clamp(0, size.width), alto);
      x += ancho;
    }
    path.close();
    canvas.drawPath(path, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_Troquel old) => old.color != color;
}

/// Línea punteada entre secciones del papel (como la que imprime la térmica).
class Corte extends StatelessWidget {
  const Corte({super.key});

  @override
  Widget build(BuildContext context) {
    final color = Papel.de(context).corte;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: LayoutBuilder(
        builder: (context, r) {
          final n = (r.maxWidth / 7).floor();
          return Row(
            children: [
              for (var i = 0; i < n; i++)
                Container(
                  width: 4,
                  height: 1.5,
                  margin: const EdgeInsets.only(right: 3),
                  color: color,
                ),
            ],
          );
        },
      ),
    );
  }
}

/// Cuánto lleva esperando: una barra que se llena hasta los 15 minutos y ahí
/// pasa a rojo. Se lee de lejos, sin leer el número.
class CronometroComanda extends StatelessWidget {
  const CronometroComanda({
    super.key,
    required this.minutos,
    required this.atrasada,
    this.limite = 15,
  });

  final int minutos;
  final bool atrasada;

  /// Minutos en que la barra se llena (y la comanda pasa a "Demora").
  final int limite;

  @override
  Widget build(BuildContext context) {
    final p = Papel.de(context);
    final color = atrasada ? p.peligro : p.aviso;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(Icons.schedule, size: 16, color: color),
            const SizedBox(width: 6),
            Text(duracion(minutos), style: impreso(tamano: 15, color: color)),
            const Spacer(),
            if (atrasada)
              Text(
                'Demora',
                style: TextStyle(
                  color: p.peligro,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
          ],
        ),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(3),
          child: LinearProgressIndicator(
            value: (minutos / limite).clamp(0.04, 1.0),
            minHeight: 6,
            color: color,
            backgroundColor: p.corte.withValues(alpha: .5),
          ),
        ),
      ],
    );
  }
}
