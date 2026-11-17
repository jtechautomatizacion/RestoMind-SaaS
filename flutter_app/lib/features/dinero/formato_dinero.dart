/// Formatos propios del dashboard. Los días van en la hora del restaurante,
/// tal como los arma el backend.
library;

const _diasSemana = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const _meses = [
  'ene',
  'feb',
  'mar',
  'abr',
  'may',
  'jun',
  'jul',
  'ago',
  'sep',
  'oct',
  'nov',
  'dic',
];

/// `Lun 17` (debajo de cada barra del gráfico).
String diaCorto(DateTime f) => '${_diasSemana[f.weekday - 1]} ${f.day}';

/// `Lun 17 nov` (tabla de ganancias por día).
String fechaTabla(DateTime f) => '${diaCorto(f)} ${_meses[f.month - 1]}';

/// Monto para la etiqueta de una barra: sin "S/" (no entra) y en "k" desde
/// mil. Por debajo de mil va EXACTO, recortando solo ".00": redondear 122.50
/// a "123" mostraba una cifra que no coincidía con ningún número real
/// (formatCompacto en dashboard.js).
String compacto(double n) {
  if (n >= 1000) {
    final miles = (n / 1000).toStringAsFixed(1);
    return '${miles.endsWith('.0') ? miles.substring(0, miles.length - 2) : miles}k';
  }
  final s = n.toStringAsFixed(2);
  return s.endsWith('.00') ? s.substring(0, s.length - 3) : s;
}
