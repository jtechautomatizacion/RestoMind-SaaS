import 'package:flutter/widgets.dart';

import 'api/api_client.dart';
import 'config.dart';
import 'plataforma/plataforma.dart';
import 'sesion.dart';

/// Las piezas compartidas de la app. Se arman UNA vez en main() y llegan a
/// cualquier pantalla con `Servicios.de(context)`.
class Servicios {
  Servicios({
    required this.api,
    required this.sesion,
    required this.plataforma,
  });

  factory Servicios.produccion() {
    final plataforma = Plataforma();
    final api = ApiClient(base: origenApi, cliente: plataforma.clienteHttp());
    return Servicios(api: api, sesion: Sesion(api), plataforma: plataforma);
  }

  final ApiClient api;
  final Sesion sesion;
  final Plataforma plataforma;

  static Servicios de(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ServiciosScope>()!.servicios;

  /// Para leerlos dentro de initState o de un callback sin suscribirse.
  static Servicios leer(BuildContext context) =>
      context.getInheritedWidgetOfExactType<ServiciosScope>()!.servicios;
}

class ServiciosScope extends InheritedWidget {
  const ServiciosScope({
    super.key,
    required this.servicios,
    required super.child,
  });

  final Servicios servicios;

  @override
  bool updateShouldNotify(ServiciosScope oldWidget) =>
      servicios != oldWidget.servicios;
}
