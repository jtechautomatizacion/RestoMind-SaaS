import '../../../core/formato.dart';
import 'modelos.dart';

/// Reporte imprimible del cierre de un turno (diseño de
/// frontend/js/cierre-caja-print.js): el resultado primero y GRANDE, para que
/// el dueño lo entienda en dos segundos; esperado contra contado; la
/// diferencia; y recién después los detalles, más chicos.
///
/// Autocontenido: estilos en línea, sin scripts, sin recursos externos y sin
/// QR (la CSP no permite nada de eso, y un QR de un servicio externo dejaba un
/// ícono roto en el papel). Pensado para A4 o PDF, no para la térmica.
String reporteCierreHtml(
  Turno t, {
  required String negocio,
  required DateTime impreso,
}) {
  final r = t.resultado;
  final turno = t.nombreTurno == null ? '' : ' · Turno ${html(t.nombreTurno)}';
  final razon = (t.razonDiscrepancia ?? '').trim().isEmpty
      ? ''
      : '''
    <div class="razon">
      <div class="razon-etiqueta">¿Por qué no cuadró?</div>
      <div class="razon-texto">${html(t.razonDiscrepancia)}</div>
    </div>''';

  return '''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Cierre de caja ${html(t.fecha)}</title>
<style>
  @page { size: A4; margin: 12mm; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #333; line-height: 1.5; }
  .hoja { max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }
  .cabecera { background: #0E7C7B; color: #fff; padding: 20px; text-align: center; }
  .negocio { font-size: 22px; font-weight: 900; }
  .cuando { font-size: 12px; opacity: .9; }
  .resultado { padding: 28px 20px; text-align: center; border-bottom: 3px solid #e5e7eb; }
  .resultado.exito { background: #dcfce7; color: #15803D; }
  .resultado.aviso { background: #fef3c7; color: #B45309; }
  .resultado.peligro { background: #fee2e2; color: #DC2626; }
  .sello { display: inline-block; width: 64px; height: 64px; line-height: 58px; border-radius: 50%; border: 4px solid currentColor; font-size: 34px; font-weight: 900; margin-bottom: 10px; }
  .resultado-texto { font-size: 24px; font-weight: 900; letter-spacing: .03em; }
  .variacion { font-size: 14px; color: #333; opacity: .8; }
  .numeros { display: flex; gap: 20px; padding: 24px; background: #fafafa; border-bottom: 2px solid #e5e7eb; }
  .numero { flex: 1; text-align: center; padding: 16px; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; }
  .etiqueta { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; font-weight: 700; margin-bottom: 6px; }
  .valor { font-size: 28px; font-weight: 900; color: #1a1a1a; font-variant-numeric: tabular-nums; }
  .diferencia { padding: 24px; text-align: center; border-bottom: 2px solid #e5e7eb; }
  .diferencia .valor { font-size: 32px; }
  .diferencia .valor.cero { color: #15803D; }
  .diferencia .valor.con-dif { color: #DC2626; }
  .detalles { padding: 24px; background: #f9fafb; }
  .fila { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #e5e7eb; font-size: 14px; }
  .fila:last-child { border-bottom: none; }
  .fila span:first-child { color: #6b7280; font-weight: 600; }
  .fila span:last-child { font-weight: 700; color: #1a1a1a; font-variant-numeric: tabular-nums; }
  .razon { margin-top: 16px; padding: 12px; background: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 4px; }
  .razon-etiqueta { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #92400e; }
  .razon-texto { font-size: 13px; color: #78350f; }
  .firmas { display: flex; gap: 24px; padding: 32px 24px 24px; border-bottom: 2px solid #e5e7eb; }
  .firma { flex: 1; text-align: center; font-size: 11px; color: #6b7280; font-weight: 600; }
  .firma-linea { border-top: 1px solid #1a1a1a; margin-top: 40px; margin-bottom: 4px; }
  .pie { padding: 14px; text-align: center; font-size: 10px; color: #9ca3af; background: #f3f4f6; }
</style>
</head>
<body>
<div class="hoja">
  <div class="cabecera">
    <div class="negocio">${html(negocio)}</div>
    <div class="cuando">${html(fechaLarga(t.fecha))} · ${hora(t.cerradoEn)}$turno</div>
  </div>

  <div class="resultado ${r.tipo.name}">
    <div class="sello">${_sello(r)}</div>
    <div class="resultado-texto">${html(r.tituloReporte)}</div>
    <div class="variacion">Variación: ${t.variacionPct.toStringAsFixed(2)}%</div>
  </div>

  <div class="numeros">
    <div class="numero"><div class="etiqueta">Esperado</div><div class="valor">${soles(t.saldoEsperado)}</div></div>
    <div class="numero"><div class="etiqueta">Contado</div><div class="valor">${soles(t.saldoContado)}</div></div>
  </div>

  <div class="diferencia">
    <div class="etiqueta">Diferencia</div>
    <div class="valor ${t.diferencia.abs() < 0.01 ? 'cero' : 'con-dif'}">${conSigno(t.diferencia)}</div>
  </div>

  <div class="detalles">
    <div class="fila"><span>Saldo inicial</span><span>${soles(t.saldoInicial)}</span></div>
    <div class="fila"><span>Ventas en efectivo</span><span>${soles(t.ventasEfectivo)}</span></div>
    <div class="fila"><span>Ventas por Yape/Plin (fuera del conteo)</span><span>${soles(t.ventasYape)}</span></div>
    <div class="fila"><span>Gastos en efectivo</span><span>${soles(t.gastosEfectivo)}</span></div>
    <div class="fila"><span>Retiros personales</span><span>${soles(t.retirosPersonales)}</span></div>
    $razon
  </div>

  <div class="firmas">
    <div class="firma"><div class="firma-linea"></div>Cerrado por:<br>${html(t.cerradoPor ?? '-')}</div>
    <div class="firma"><div class="firma-linea"></div>Revisado por<br>(si corresponde)</div>
  </div>

  <div class="pie">
    Registro: CIERRE-${html(t.fecha)}-${t.id}<br>
    RestoMind · Cierre de caja · impreso el ${fechaHora(impreso)}
  </div>
</div>
</body>
</html>''';
}

/// Un signo y no un emoji: el papel lo imprime cualquier navegador con
/// cualquier fuente.
String _sello(Resultado r) => switch (r) {
  Resultado.cuadrado => 'OK',
  Resultado.grave => 'X',
  Resultado.leve || Resultado.automatico => '!',
};

/// `+S/ 2.50` / `-S/ 2.50`: sobra o falta, dicho de una.
String conSigno(double monto) =>
    '${monto < 0 ? '-' : '+'}${soles(monto.abs())}';

const _dias = [
  'lunes',
  'martes',
  'miércoles',
  'jueves',
  'viernes',
  'sábado',
  'domingo',
];
const _meses = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];

/// `2026-11-17` → `martes, 17 de noviembre de 2026`. La fecha del turno ya
/// está en el día del restaurante: se lee tal cual, sin pasar por UTC.
String fechaLarga(String iso) {
  final f = DateTime.tryParse(iso);
  if (f == null) return iso;
  return '${_dias[f.weekday - 1]}, ${f.day} de ${_meses[f.month - 1]} '
      'de ${f.year}';
}
