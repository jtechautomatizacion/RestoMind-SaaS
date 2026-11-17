import 'package:flutter/material.dart';

import 'papel.dart';

/// Paleta de RestoMind: la misma de frontend/css/style.css, llevada a Material 3.
///
/// Tres decisiones heredadas que no conviene deshacer:
///  1. Las superficies son grises azulados que suben de tono, no negro puro.
///  2. El primario se INVIERTE entre temas: azul claro con texto oscuro en el
///     oscuro, azul profundo con texto blanco en el claro (como Android).
///  3. El primario es azul y no cálido: ámbar = "esperando la cuenta",
///     verde = éxito, rojo = peligro, teal = dinero. Un primario cálido
///     competiría con esos avisos justo donde importan.
@immutable
class Colores extends ThemeExtension<Colores> {
  const Colores({
    required this.fondo,
    required this.superficie,
    required this.superficieAlt,
    required this.texto,
    required this.textoSuave,
    required this.borde,
    required this.exito,
    required this.exitoFondo,
    required this.peligro,
    required this.peligroFondo,
    required this.aviso,
    required this.avisoFondo,
    required this.dinero,
    required this.sobreSemantico,
    required this.mesaLibre,
    required this.mesaCocina,
    required this.mesaCobrar,
  });

  final Color fondo;
  final Color superficie;
  final Color superficieAlt;
  final Color texto;
  final Color textoSuave;
  final Color borde;
  final Color exito;
  final Color exitoFondo;
  final Color peligro;
  final Color peligroFondo;
  final Color aviso;
  final Color avisoFondo;
  final Color dinero;

  /// Texto encima de un fondo semántico relleno (un chip rojo, una barra verde).
  final Color sobreSemantico;

  /// Degradado del disco de la mesa (claro arriba-izquierda → oscuro): libre,
  /// en cocina y esperando la cuenta.
  final List<Color> mesaLibre;
  final List<Color> mesaCocina;
  final List<Color> mesaCobrar;

  static const oscuro = Colores(
    fondo: Color(0xFF0F1317),
    superficie: Color(0xFF171C21),
    superficieAlt: Color(0xFF1F262D),
    texto: Color(0xFFE4E7EA),
    textoSuave: Color(0xFF9AA4AF),
    borde: Color(0xFF2B333C),
    exito: Color(0xFF4ADE80),
    exitoFondo: Color(0xFF0E2A1B),
    peligro: Color(0xFFFB7185),
    peligroFondo: Color(0xFF331519),
    aviso: Color(0xFFFBBF24),
    avisoFondo: Color(0xFF332708),
    dinero: Color(0xFF2DD4BF),
    sobreSemantico: Color(0xFF10151B),
    mesaLibre: [Color(0xFF39424D), Color(0xFF2A323B), Color(0xFF1B222A)],
    mesaCocina: [Color(0xFFBBD5F7), Color(0xFF7FB0F2), Color(0xFF3D6DA8)],
    mesaCobrar: [Color(0xFFF3D07A), Color(0xFFE8B33D), Color(0xFF8A6A15)],
  );

  static const claro = Colores(
    fondo: Color(0xFFF4F6F8),
    superficie: Color(0xFFFFFFFF),
    superficieAlt: Color(0xFFEDF1F5),
    texto: Color(0xFF161D26),
    textoSuave: Color(0xFF5C6773),
    borde: Color(0xFFDCE3EA),
    exito: Color(0xFF15803D),
    exitoFondo: Color(0xFFDCFCE7),
    peligro: Color(0xFFDC2626),
    peligroFondo: Color(0xFFFEE2E2),
    aviso: Color(0xFFB45309),
    avisoFondo: Color(0xFFFEF3C7),
    dinero: Color(0xFF0E7C7B),
    sobreSemantico: Color(0xFFFFFFFF),
    mesaLibre: [Color(0xFFFFFFFF), Color(0xFFE4E9EF), Color(0xFFC3CCD6)],
    mesaCocina: [Color(0xFFBBD5F7), Color(0xFF3D7DC4), Color(0xFF1B4C85)],
    mesaCobrar: [Color(0xFFF7DE9A), Color(0xFFE0A526), Color(0xFF8A6A15)],
  );

  static Colores de(BuildContext context) =>
      Theme.of(context).extension<Colores>()!;

  @override
  Colores copyWith() => this;

  @override
  Colores lerp(ThemeExtension<Colores>? other, double t) =>
      t < .5 ? this : (other as Colores? ?? this);
}

const fuenteMono = 'IBM Plex Mono';

/// Números alineados en columnas (importes en tablas y tickets).
const cifras = [FontFeature.tabularFigures()];

ThemeData temaRestoMind(Brightness brillo) {
  final oscuro = brillo == Brightness.dark;
  final c = oscuro ? Colores.oscuro : Colores.claro;
  final primario = oscuro ? const Color(0xFF7FB0F2) : const Color(0xFF1B5EA8);
  final sobrePrimario = oscuro ? const Color(0xFF0A2440) : Colors.white;
  final esquema = ColorScheme(
    brightness: brillo,
    primary: primario,
    onPrimary: sobrePrimario,
    secondary: c.dinero,
    onSecondary: c.sobreSemantico,
    error: c.peligro,
    onError: c.sobreSemantico,
    surface: c.superficie,
    onSurface: c.texto,
    surfaceContainerLowest: c.fondo,
    surfaceContainerLow: c.superficie,
    surfaceContainer: c.superficie,
    surfaceContainerHigh: c.superficieAlt,
    surfaceContainerHighest: c.superficieAlt,
    onSurfaceVariant: c.textoSuave,
    outline: c.borde,
    outlineVariant: c.borde,
    secondaryContainer: oscuro
        ? const Color(0xFF22344B)
        : const Color(0xFFDCE8F8),
    onSecondaryContainer: primario,
  );
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: esquema,
    brightness: brillo,
    fontFamily: 'Inter',
    scaffoldBackgroundColor: c.fondo,
    extensions: [c, oscuro ? Papel.oscuro : Papel.claro],
  );
  // Escala fija (12 / 14 / 16 / 20 / 28 / 40): pocos tamaños, bien separados,
  // para que la jerarquía se lea de un vistazo y no por diferencias de 1 px.
  final texto = base.textTheme
      .copyWith(
        displaySmall: const TextStyle(
          fontSize: 40,
          fontWeight: FontWeight.w800,
          height: 1.1,
          letterSpacing: -0.5,
        ),
        headlineSmall: const TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.w800,
          height: 1.15,
          letterSpacing: -0.3,
        ),
        titleLarge: const TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w700,
          height: 1.2,
        ),
        titleMedium: const TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          height: 1.3,
        ),
        bodyLarge: const TextStyle(fontSize: 16, height: 1.45),
        bodyMedium: const TextStyle(fontSize: 14, height: 1.45),
        bodySmall: TextStyle(fontSize: 12, height: 1.4, color: c.textoSuave),
        labelLarge: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
      )
      .apply(fontFamily: 'Inter', bodyColor: c.texto, displayColor: c.texto);
  final redondeo = BorderRadius.circular(12);
  return base.copyWith(
    textTheme: texto,
    appBarTheme: AppBarTheme(
      backgroundColor: c.superficie,
      foregroundColor: c.texto,
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      shape: Border(bottom: BorderSide(color: c.borde)),
      titleTextStyle: TextStyle(
        fontFamily: 'Inter',
        fontSize: 16,
        fontWeight: FontWeight.w700,
        color: c.texto,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: c.superficie,
      indicatorColor: esquema.secondaryContainer,
      surfaceTintColor: Colors.transparent,
      height: 66,
      labelTextStyle: WidgetStateProperty.resolveWith(
        (s) => TextStyle(
          fontFamily: 'Inter',
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: s.contains(WidgetState.selected) ? primario : c.textoSuave,
        ),
      ),
    ),
    cardTheme: CardThemeData(
      color: c.superficie,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: c.borde),
      ),
    ),
    dividerTheme: DividerThemeData(color: c.borde, space: 1, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: oscuro ? c.fondo : c.superficie,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: redondeo,
        borderSide: BorderSide(color: c.borde),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: redondeo,
        borderSide: BorderSide(color: c.borde),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: redondeo,
        borderSide: BorderSide(color: primario, width: 2),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: redondeo,
        borderSide: BorderSide(color: c.peligro),
      ),
      labelStyle: TextStyle(color: c.textoSuave),
      floatingLabelStyle: TextStyle(
        color: primario,
        fontWeight: FontWeight.w600,
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(48, 48),
        shape: RoundedRectangleBorder(borderRadius: redondeo),
        textStyle: const TextStyle(
          fontFamily: 'Inter',
          fontWeight: FontWeight.w700,
          fontSize: 15,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(48, 48),
        foregroundColor: c.texto,
        side: BorderSide(color: c.borde),
        shape: RoundedRectangleBorder(borderRadius: redondeo),
        textStyle: const TextStyle(
          fontFamily: 'Inter',
          fontWeight: FontWeight.w600,
          fontSize: 15,
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(48, 44),
        textStyle: const TextStyle(
          fontFamily: 'Inter',
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: c.superficie,
      selectedColor: primario,
      side: BorderSide(color: c.borde),
      labelStyle: TextStyle(
        fontFamily: 'Inter',
        fontWeight: FontWeight.w600,
        color: c.texto,
      ),
      secondaryLabelStyle: TextStyle(
        fontFamily: 'Inter',
        fontWeight: FontWeight.w600,
        color: sobrePrimario,
      ),
      checkmarkColor: sobrePrimario,
      shape: const StadiumBorder(),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: redondeo),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: c.superficie,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: c.superficie,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
    ),
  );
}
