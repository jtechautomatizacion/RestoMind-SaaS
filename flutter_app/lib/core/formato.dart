/// Formatos de pantalla: dinero en soles y fechas en la hora del local.
library;

/// `S/ 1,284.50`. Siempre dos decimales: nunca redondear un importe para
/// "que se vea mejor" (ver formatCompacto en CLAUDE.md, el bug de 122.50→123).
String soles(num? monto) => 'S/ ${numero(monto)}';

/// `1,284.50` (separador de miles con coma, como en Perú).
String numero(num? monto) {
  final v = (monto ?? 0).toDouble();
  final negativo = v < 0;
  final partes = v.abs().toStringAsFixed(2).split('.');
  final entero = partes[0].replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => ',',
  );
  return '${negativo ? '-' : ''}$entero.${partes[1]}';
}

/// Lee un número que puede venir como int, double o texto.
double aDouble(Object? v) => switch (v) {
  final num n => n.toDouble(),
  final String s => double.tryParse(s.replaceAll(',', '.')) ?? 0,
  _ => 0,
};

/// Las fechas del backend son UTC SIN zona ("2026-11-17T15:04:05"). Se leen
/// como UTC y se pasan a la hora del aparato, que es la del local.
DateTime? fechaLocal(Object? iso) {
  if (iso is! String || iso.isEmpty) return null;
  final conZona = RegExp(r'(Z|[+-]\d\d:?\d\d)$').hasMatch(iso)
      ? iso
      : '${iso}Z';
  return DateTime.tryParse(conZona)?.toLocal();
}

String _dos(int n) => n.toString().padLeft(2, '0');

/// `17/11/2026`
String fecha(DateTime? f) =>
    f == null ? '—' : '${_dos(f.day)}/${_dos(f.month)}/${f.year}';

/// `17/11/2026 20:15`
String fechaHora(DateTime? f) =>
    f == null ? '—' : '${fecha(f)} ${_dos(f.hour)}:${_dos(f.minute)}';

/// `20:15`
String hora(DateTime? f) =>
    f == null ? '—' : '${_dos(f.hour)}:${_dos(f.minute)}';

/// Fecha de calendario para la API: `2026-11-17`.
String fechaIso(DateTime f) => '${f.year}-${_dos(f.month)}-${_dos(f.day)}';

/// "hace 5 min", "hace 2 h"
String haceCuanto(DateTime? f, {DateTime? ahora}) {
  if (f == null) return '';
  final d = (ahora ?? DateTime.now()).difference(f);
  if (d.inMinutes < 1) return 'recién';
  if (d.inMinutes < 60) return 'hace ${d.inMinutes} min';
  return 'hace ${d.inHours} h';
}

/// Tiempo de espera legible: "8 min", "2 h 15 min", "3 d". Un pedido olvidado
/// días en cocina como "4320 min" no lo lee nadie.
String duracion(int minutos) {
  if (minutos < 60) return '$minutos min';
  if (minutos < 1440) {
    final m = minutos % 60;
    return '${minutos ~/ 60} h${m == 0 ? '' : ' $m min'}';
  }
  return '${minutos ~/ 1440} d';
}

/// Escapa texto para meterlo en un documento HTML de impresión.
String html(Object? texto) => '${texto ?? ''}'
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
