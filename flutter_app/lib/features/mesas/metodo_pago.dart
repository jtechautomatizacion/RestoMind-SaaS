import 'package:flutter/material.dart';

import 'modelos.dart';

/// Con qué paga. Dos botones y no un desplegable: se elige con el cliente
/// esperando, y un desplegable son dos toques y una lista que tapa la
/// pantalla. Arranca en Efectivo, el caso común, así que suele ser cero toques.
class SelectorMetodoPago extends StatelessWidget {
  const SelectorMetodoPago({
    super.key,
    required this.valor,
    required this.alCambiar,
  });

  final MetodoPago valor;
  final ValueChanged<MetodoPago> alCambiar;

  @override
  Widget build(BuildContext context) => SegmentedButton<MetodoPago>(
    segments: const [
      ButtonSegment(
        value: MetodoPago.efectivo,
        icon: Icon(Icons.payments_outlined),
        label: Text('Efectivo'),
      ),
      ButtonSegment(
        value: MetodoPago.yape,
        icon: Icon(Icons.phone_iphone),
        label: Text('Yape/Plin'),
      ),
    ],
    selected: {valor},
    onSelectionChanged: (v) => alCambiar(v.first),
  );
}
