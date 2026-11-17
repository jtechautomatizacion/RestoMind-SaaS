import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'core/servicios.dart';
import 'core/sesion.dart';
import 'design/tema.dart';
import 'features/login/login_page.dart';
import 'shell/shell.dart';

class RestoMindApp extends StatefulWidget {
  const RestoMindApp({super.key, required this.servicios});

  final Servicios servicios;

  @override
  State<RestoMindApp> createState() => _RestoMindAppState();
}

class _RestoMindAppState extends State<RestoMindApp> {
  static const _clavetema = 'tema';
  late ThemeMode _tema =
      widget.servicios.plataforma.preferencia(_clavetema) == 'claro'
      ? ThemeMode.light
      : ThemeMode.dark; // Oscuro por defecto, como la app de siempre.

  @override
  void initState() {
    super.initState();
    widget.servicios.sesion.iniciar();
  }

  void _alternarTema() {
    setState(
      () => _tema = _tema == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark,
    );
    widget.servicios.plataforma.guardarPreferencia(
      _clavetema,
      _tema == ThemeMode.light ? 'claro' : 'oscuro',
    );
  }

  @override
  Widget build(BuildContext context) => ServiciosScope(
    servicios: widget.servicios,
    child: MaterialApp(
      title: 'RestoMind',
      debugShowCheckedModeBanner: false,
      theme: temaRestoMind(Brightness.light),
      darkTheme: temaRestoMind(Brightness.dark),
      themeMode: _tema,
      locale: const Locale('es', 'PE'),
      supportedLocales: const [Locale('es', 'PE'), Locale('es')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      home: ListenableBuilder(
        listenable: widget.servicios.sesion,
        builder: (context, _) => switch (widget.servicios.sesion.estado) {
          EstadoSesion.comprobando => const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          ),
          EstadoSesion.anonima => LoginPage(alternarTema: _alternarTema),
          // La clave por usuario descarta el estado de la sesión anterior.
          EstadoSesion.autenticada => Shell(
            key: ValueKey(widget.servicios.sesion.usuario!.email),
            alternarTema: _alternarTema,
          ),
        },
      ),
    ),
  );
}
