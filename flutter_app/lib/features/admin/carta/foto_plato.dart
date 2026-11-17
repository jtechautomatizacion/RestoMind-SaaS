import 'package:flutter/material.dart';

import '../../../core/config.dart';
import '../../../design/tema.dart';

/// Miniatura de la foto de un plato, o un marco vacío si no tiene.
///
/// [version] cambia cuando se reemplaza la foto: el servidor la guarda siempre
/// con el mismo nombre (`7.jpg`), así que sin ese parámetro el navegador
/// seguiría mostrando la anterior.
class FotoPlato extends StatelessWidget {
  const FotoPlato({super.key, required this.url, this.version, this.lado = 52});

  final String? url;
  final int? version;
  final double lado;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final vacio = Container(
      width: lado,
      height: lado,
      color: c.superficieAlt,
      child: Icon(Icons.image_outlined, color: c.textoSuave, size: lado * .45),
    );
    final ruta = url;
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: ruta == null
          ? vacio
          : Image.network(
              '$origenApi$ruta${version == null ? '' : '?v=$version'}',
              width: lado,
              height: lado,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => vacio,
            ),
    );
  }
}
