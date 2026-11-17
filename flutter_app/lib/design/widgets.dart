import 'package:flutter/material.dart';

import '../core/api/api_error.dart';
import 'tema.dart';

/// Piezas de interfaz que usan TODAS las pantallas. Antes de escribir un widget
/// nuevo en una pantalla, revisar si ya está acá.

enum TipoAviso { exito, error, info }

/// Aviso corto abajo de la pantalla. Para errores de la API, pasar el
/// [ApiError] directo: su mensaje ya está pensado para el usuario.
/// [accion] agrega un botón al aviso (p. ej. "Imprimir" tras mandar un pedido),
/// y lo deja más tiempo en pantalla para que alcance a tocarse.
void avisar(
  BuildContext context,
  Object mensaje, {
  TipoAviso tipo = TipoAviso.info,
  (String, VoidCallback)? accion,
}) {
  final c = Colores.de(context);
  final texto = mensaje is ApiError ? mensaje.mensaje : '$mensaje';
  final t = mensaje is ApiError ? TipoAviso.error : tipo;
  final (fondo, frente) = switch (t) {
    TipoAviso.exito => (c.exito, c.sobreSemantico),
    TipoAviso.error => (c.peligro, c.sobreSemantico),
    TipoAviso.info => (c.texto, c.fondo),
  };
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        backgroundColor: fondo,
        content: Text(
          texto,
          style: TextStyle(color: frente, fontWeight: FontWeight.w600),
        ),
        duration: Duration(
          seconds: t == TipoAviso.error || accion != null ? 6 : 3,
        ),
        action: accion == null
            ? null
            : SnackBarAction(
                label: accion.$1,
                textColor: frente,
                onPressed: accion.$2,
              ),
      ),
    );
}

/// Pregunta antes de una acción que no tiene "deshacer" (cobrar, cerrar caja,
/// eliminar). Devuelve true solo si se confirmó.
Future<bool> confirmar(
  BuildContext context, {
  required String titulo,
  required String mensaje,
  required String accion,
  bool peligrosa = false,
}) async {
  final c = Colores.de(context);
  final r = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(titulo),
      content: Text(mensaje),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('Cancelar'),
        ),
        FilledButton(
          style: peligrosa
              ? FilledButton.styleFrom(
                  backgroundColor: c.peligro,
                  foregroundColor: c.sobreSemantico,
                )
              : null,
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(accion),
        ),
      ],
    ),
  );
  return r ?? false;
}

enum TipoEstado { exito, aviso, peligro, info, neutro }

/// Pastilla de estado: "Caja abierta", "Crítico", "Aceptada por SUNAT".
class Pastilla extends StatelessWidget {
  const Pastilla(
    this.texto, {
    super.key,
    this.tipo = TipoEstado.neutro,
    this.icono,
  });

  final String texto;
  final TipoEstado tipo;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final primario = Theme.of(context).colorScheme.primary;
    final (fondo, frente) = switch (tipo) {
      TipoEstado.exito => (c.exitoFondo, c.exito),
      TipoEstado.aviso => (c.avisoFondo, c.aviso),
      TipoEstado.peligro => (c.peligroFondo, c.peligro),
      TipoEstado.info => (
        Theme.of(context).colorScheme.secondaryContainer,
        primario,
      ),
      TipoEstado.neutro => (c.superficieAlt, c.textoSuave),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: fondo,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icono != null) ...[
            Icon(icono, size: 14, color: frente),
            const SizedBox(width: 4),
          ],
          // Flexible: un aviso largo parte en líneas en vez de salirse.
          Flexible(
            child: Text(
              texto,
              style: TextStyle(
                color: frente,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Título de pantalla con subtítulo y una acción opcional a la derecha.
class Encabezado extends StatelessWidget {
  const Encabezado({
    super.key,
    required this.titulo,
    this.subtitulo,
    this.accion,
  });

  final String titulo;
  final String? subtitulo;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  titulo,
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (subtitulo != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      subtitulo!,
                      style: TextStyle(color: c.textoSuave, fontSize: 13),
                    ),
                  ),
              ],
            ),
          ),
          if (accion != null) accion!,
        ],
      ),
    );
  }
}

/// Título de una sección dentro de una pantalla ("Los 5 platos que más dejan").
/// En minúsculas normales: las mayúsculas espaciadas gritan sin agregar nada.
class TituloSeccion extends StatelessWidget {
  const TituloSeccion(this.texto, {super.key});
  final String texto;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 22, bottom: 10),
    child: Text(texto, style: Theme.of(context).textTheme.titleMedium),
  );
}

/// Pantalla vacía con explicación: qué va a aparecer acá y cómo se llena.
class Vacio extends StatelessWidget {
  const Vacio({
    super.key,
    required this.titulo,
    this.mensaje,
    this.icono = Icons.inbox_outlined,
    this.accion,
  });

  final String titulo;
  final String? mensaje;
  final IconData icono;
  final Widget? accion;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icono, size: 44, color: c.textoSuave),
            const SizedBox(height: 12),
            Text(
              titulo,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            if (mensaje != null) ...[
              const SizedBox(height: 6),
              Text(
                mensaje!,
                textAlign: TextAlign.center,
                style: TextStyle(color: c.textoSuave),
              ),
            ],
            if (accion != null) ...[const SizedBox(height: 16), accion!],
          ],
        ),
      ),
    );
  }
}

/// Error de carga con botón para reintentar.
class ErrorCarga extends StatelessWidget {
  const ErrorCarga({super.key, required this.error, required this.reintentar});

  final Object error;
  final VoidCallback reintentar;

  @override
  Widget build(BuildContext context) => Vacio(
    icono: error is ApiError && (error as ApiError).esRed
        ? Icons.wifi_off
        : Icons.error_outline,
    titulo: 'No se pudo cargar',
    mensaje: error is ApiError ? (error as ApiError).mensaje : '$error',
    accion: OutlinedButton.icon(
      onPressed: reintentar,
      icon: const Icon(Icons.refresh),
      label: const Text('Reintentar'),
    ),
  );
}

/// Carga datos con un Future y muestra cargando / error / contenido. Se recarga
/// con [CargadorState.recargar] o arrastrando hacia abajo.
class Cargador<T> extends StatefulWidget {
  const Cargador({super.key, required this.cargar, required this.construir});

  final Future<T> Function() cargar;
  final Widget Function(
    BuildContext context,
    T datos,
    Future<void> Function() recargar,
  )
  construir;

  @override
  State<Cargador<T>> createState() => CargadorState<T>();
}

class CargadorState<T> extends State<Cargador<T>> {
  late Future<T> _futuro = widget.cargar();

  Future<void> recargar() async {
    final f = widget.cargar();
    // Con llaves: una flecha devolvería el Future y setState lo rechaza.
    setState(() {
      _futuro = f;
    });
    try {
      await f;
    } catch (_) {
      // El error se muestra en el build.
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<T>(
    future: _futuro,
    builder: (context, s) {
      if (s.hasError) return ErrorCarga(error: s.error!, reintentar: recargar);
      if (!s.hasData && s.connectionState != ConnectionState.done) {
        return const Center(child: CircularProgressIndicator());
      }
      return RefreshIndicator(
        onRefresh: recargar,
        child: widget.construir(context, s.data as T, recargar),
      );
    },
  );
}

/// Limita el ancho del contenido en pantallas grandes (tablet, PC) y pone el
/// margen lateral de siempre.
class Contenido extends StatelessWidget {
  const Contenido({
    super.key,
    required this.child,
    this.ancho = 960,
    this.padding = const EdgeInsets.all(16),
  });

  final Widget child;
  final double ancho;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.topCenter,
    child: ConstrainedBox(
      constraints: BoxConstraints(maxWidth: ancho),
      child: Padding(padding: padding, child: child),
    ),
  );
}

/// Fila "etiqueta ........ valor" de resúmenes de dinero.
class FilaMonto extends StatelessWidget {
  const FilaMonto(
    this.etiqueta,
    this.valor, {
    super.key,
    this.color,
    this.fuerte = false,
  });

  final String etiqueta;
  final String valor;
  final Color? color;
  final bool fuerte;

  @override
  Widget build(BuildContext context) {
    final estilo = TextStyle(
      fontWeight: fuerte ? FontWeight.w800 : FontWeight.w500,
      fontSize: fuerte ? 16 : 14,
      fontFeatures: cifras,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(child: Text(etiqueta, style: estilo)),
          Text(valor, style: estilo.copyWith(color: color)),
        ],
      ),
    );
  }
}

/// Tarjeta con número grande (ventas de hoy, ganancia).
class Indicador extends StatelessWidget {
  const Indicador({
    super.key,
    required this.etiqueta,
    required this.valor,
    this.color,
    this.nota,
  });

  final String etiqueta;
  final String valor;
  final Color? color;
  final String? nota;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              etiqueta,
              style: TextStyle(
                color: c.textoSuave,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              valor,
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w800,
                color: color,
                fontFeatures: cifras,
              ),
            ),
            if (nota != null)
              Text(nota!, style: TextStyle(color: c.textoSuave, fontSize: 12)),
          ],
        ),
      ),
    );
  }
}

/// Muestra un formulario en una hoja inferior que respeta el teclado.
Future<T?> mostrarHoja<T>(BuildContext context, WidgetBuilder builder) =>
    showModalBottomSheet<T>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      constraints: const BoxConstraints(maxWidth: 640),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(ctx).bottom),
        child: builder(ctx),
      ),
    );
