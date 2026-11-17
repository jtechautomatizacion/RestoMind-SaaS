import 'package:flutter/material.dart';

import '../../core/formato.dart';
import '../../design/papel.dart';
import '../../design/tema.dart';
import 'modelos.dart';

/// A partir de acá una mesa que espera "ya es mucho". Es el mismo umbral con
/// el que el monitor de cocina pinta una comanda atrasada: las dos pantallas
/// dicen lo mismo sobre la misma mesa.
const minutosAlerta = 15;

/// Ícono de la mesa con relieve: disco con degradado radial, sombra en el
/// piso, brillo arriba a la izquierda y cuatro sillas. Formas planas con
/// degradado, sin desenfoques: cuesta lo mismo que un ícono plano.
class IconoMesa extends StatelessWidget {
  const IconoMesa({super.key, required this.estado, this.tamano = 48});

  final EstadoMesa estado;
  final double tamano;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return CustomPaint(
      size: Size.square(tamano),
      painter: _PintorMesa(
        tapa: switch (estado) {
          EstadoMesa.libre => c.mesaLibre,
          EstadoMesa.cocinando => c.mesaCocina,
          EstadoMesa.porCobrar => c.mesaCobrar,
        },
        sombra: c.texto.withValues(alpha: .16),
      ),
    );
  }
}

class _PintorMesa extends CustomPainter {
  _PintorMesa({required this.tapa, required this.sombra});

  final List<Color> tapa;
  final Color sombra;

  @override
  void paint(Canvas canvas, Size size) {
    // Coordenadas del SVG original (viewBox 24x24), escaladas.
    final k = size.width / 24;
    Offset p(double x, double y) => Offset(x * k, y * k);

    canvas.drawOval(
      Rect.fromCenter(center: p(12, 21.1), width: 13.2 * k, height: 2.7 * k),
      Paint()..color = sombra,
    );
    for (final (x, y) in const [
      (12.0, 2.6),
      (12.0, 19.3),
      (2.6, 11.0),
      (21.4, 11.0),
    ]) {
      final r = Rect.fromCircle(center: p(x, y), radius: 1.65 * k);
      canvas.drawCircle(
        r.center,
        r.width / 2,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [tapa[1], tapa[2]],
          ).createShader(r),
      );
    }
    final disco = Rect.fromCircle(center: p(12, 11), radius: 6 * k);
    canvas.drawCircle(
      disco.center,
      disco.width / 2,
      Paint()
        ..shader = RadialGradient(
          center: const Alignment(-.35, -.4),
          radius: 1.05,
          colors: tapa,
          stops: const [0, .55, 1],
        ).createShader(disco),
    );
    canvas.drawOval(
      Rect.fromCenter(center: p(9.4, 8.3), width: 5 * k, height: 2.6 * k),
      Paint()..color = Colors.white.withValues(alpha: .35),
    );
  }

  @override
  bool shouldRepaint(_PintorMesa old) =>
      old.tapa != tapa || old.sombra != sombra;
}

/// Una mesa en la grilla. Además del color dice el estado con palabras: en
/// una grilla grande no puede depender solo del color.
class TarjetaMesa extends StatelessWidget {
  const TarjetaMesa({
    super.key,
    required this.mesa,
    required this.estado,
    this.onTap,
    this.minutos,
  });

  final Mesa mesa;
  final EstadoMesa estado;

  /// null = apagada (quien solo cobra no toma pedidos en una mesa libre).
  final VoidCallback? onTap;

  /// Hace cuánto espera (solo en "Atiendo solo").
  final int? minutos;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final esquema = Theme.of(context).colorScheme;
    final (fondoFranja, textoFranja, etiqueta) = switch (estado) {
      EstadoMesa.libre => (c.superficieAlt, c.textoSuave, 'Libre'),
      EstadoMesa.cocinando => (esquema.primary, esquema.onPrimary, 'En cocina'),
      EstadoMesa.porCobrar => (c.aviso, c.sobreSemantico, 'Por cobrar'),
    };
    final espera = minutos;
    final urgente = espera != null && espera >= minutosAlerta;
    final detalle = estado == EstadoMesa.libre
        ? '${mesa.capacidad} personas'
        : soles(mesa.cuentaActual);
    return Semantics(
      button: true,
      label: estado == EstadoMesa.libre
          ? 'Mesa ${mesa.numero} libre, ${mesa.capacidad} personas'
          : 'Mesa ${mesa.numero}, $detalle, ${etiqueta.toLowerCase()}'
                '${espera != null ? ', hace $espera minutos' : ''}',
      excludeSemantics: true,
      child: Opacity(
        opacity: onTap == null ? .45 : 1,
        child: Material(
          color: c.superficie,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
            side: BorderSide(
              color: urgente ? c.peligro : c.borde,
              width: urgente ? 2 : 1,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: onTap,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 10, 0),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // El número va "impreso": es el mismo que sale en la
                      // comanda y en la pre-cuenta.
                      Text(
                        '${mesa.numero}',
                        style: impreso(
                          tamano: 28,
                          peso: FontWeight.w500,
                          color: c.texto,
                        ),
                      ),
                      const Spacer(),
                      if (espera != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            espera < 1 ? 'recién' : "$espera'",
                            style: impreso(
                              tamano: 13,
                              color: urgente ? c.peligro : c.textoSuave,
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                // La mesa ocupa todo el alto libre de la tarjeta: es lo que
                // se reconoce de un vistazo desde lejos, no el texto.
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, caja) => Center(
                      child: IconoMesa(
                        estado: estado,
                        tamano: caja.biggest.shortestSide.clamp(32, 96),
                      ),
                    ),
                  ),
                ),
                if (mesa.ubicacion != null && mesa.ubicacion!.isNotEmpty)
                  Text(
                    mesa.ubicacion!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 12, color: c.textoSuave),
                  ),
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    detalle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: estado == EstadoMesa.libre
                        ? TextStyle(fontSize: 13, color: c.textoSuave)
                        : impreso(tamano: 15, color: c.texto),
                  ),
                ),
                // El estado es una franja de color de borde a borde: la grilla
                // se lee por color desde lejos, sin leer ninguna palabra.
                Container(
                  width: double.infinity,
                  color: fondoFranja,
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: Text(
                    etiqueta,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: textoFranja,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// "Para llevar" va DENTRO de la grilla, como una mesa más: es el mismo gesto
/// que ya conoce quien atiende y ocupa el lugar donde va a mirar. Puesto
/// aparte se vuelve una función escondida que hay que enseñar.
class TarjetaParaLlevar extends StatelessWidget {
  const TarjetaParaLlevar({super.key, required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final primario = Theme.of(context).colorScheme.primary;
    return Material(
      color: Theme.of(context).colorScheme.secondaryContainer,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: primario, width: 1.5),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(10),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.shopping_bag_outlined, size: 40, color: primario),
              const SizedBox(height: 6),
              Text(
                'Para llevar',
                textAlign: TextAlign.center,
                style: TextStyle(fontWeight: FontWeight.w800, color: primario),
              ),
              Text(
                'Se cobra al pedir',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 11, color: c.textoSuave),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
