import 'package:flutter/material.dart';

import '../../../core/formato.dart';
import '../../../design/widgets.dart';

/// Un turno de caja (CierreCajaResponse): abierto o ya cerrado.
@immutable
class Turno {
  const Turno({
    required this.id,
    required this.fecha,
    required this.saldoInicial,
    required this.estado,
    this.abiertoEn,
    this.nombreTurno,
    this.ventasEfectivo = 0,
    this.ventasYape = 0,
    this.gastosEfectivo = 0,
    this.retirosPersonales = 0,
    this.saldoEsperado = 0,
    this.saldoContado = 0,
    this.diferencia = 0,
    this.variacionPct = 0,
    this.razonDiscrepancia,
    this.cerradoEn,
    this.cerradoPor,
  });

  factory Turno.desdeJson(Map<String, dynamic> j) => Turno(
    id: (j['id'] as num).toInt(),
    fecha: j['fecha'] as String? ?? '',
    saldoInicial: aDouble(j['saldo_inicial']),
    abiertoEn: fechaLocal(j['abierto_en']),
    nombreTurno: j['nombre_turno'] as String?,
    ventasEfectivo: aDouble(j['ventas_cobradas']),
    ventasYape: aDouble(j['ventas_yape']),
    gastosEfectivo: aDouble(j['gastos_efectivo']),
    retirosPersonales: aDouble(j['retiros_personales']),
    saldoEsperado: aDouble(j['saldo_esperado']),
    saldoContado: aDouble(j['saldo_contado']),
    diferencia: aDouble(j['diferencia']),
    variacionPct: aDouble(j['variacion_pct']),
    razonDiscrepancia: j['razon_discrepancia'] as String?,
    cerradoEn: fechaLocal(j['cerrado_en']),
    cerradoPor: j['cerrado_por'] as String?,
    estado: j['estado'] as String? ?? '',
  );

  final int id;

  /// Día del restaurante, `2026-11-17` (ya en su hora local: no se convierte).
  final String fecha;
  final double saldoInicial;
  final DateTime? abiertoEn;
  final String? nombreTurno;

  /// Solo efectivo: es lo único que se espera encontrar al contar.
  final double ventasEfectivo;

  /// Informativo, fuera del arqueo: esa plata está en un celular.
  final double ventasYape;
  final double gastosEfectivo;
  final double retirosPersonales;
  final double saldoEsperado;
  final double saldoContado;
  final double diferencia;
  final double variacionPct;
  final String? razonDiscrepancia;
  final DateTime? cerradoEn;
  final String? cerradoPor;

  /// abierto | cuadrado | discrepancia_leve | discrepancia_grave |
  /// cerrado_automatico. Lo clasifica el backend, nunca esta app.
  final String estado;

  Resultado get resultado => Resultado.de(estado);
}

/// Cómo terminó un turno, en las palabras que usa cualquiera que maneja una
/// caja ("cuadró", "no cuadró"), no en las de un auditor.
enum Resultado {
  cuadrado(
    'Caja cuadrada',
    'CAJA CUADRADA',
    TipoEstado.exito,
    Icons.check_circle,
  ),
  leve(
    'No cuadró (diferencia chica)',
    'NO CUADRÓ (DIFERENCIA CHICA)',
    TipoEstado.aviso,
    Icons.warning_amber_rounded,
  ),
  grave(
    'No cuadró (diferencia grande)',
    'NO CUADRÓ (DIFERENCIA GRANDE)',
    TipoEstado.peligro,
    Icons.cancel,
  ),

  /// El admin nunca la cerró: el sistema la cerró sola al día siguiente con
  /// contado = esperado, porque no hubo conteo real. Hay que revisarla.
  automatico(
    'Se cerró sola (falta contar el dinero)',
    'SE CERRÓ SOLA (FALTA CONTAR EL DINERO)',
    TipoEstado.aviso,
    Icons.schedule,
  );

  const Resultado(this.titulo, this.tituloReporte, this.tipo, this.icono);

  final String titulo;
  final String tituloReporte;
  final TipoEstado tipo;
  final IconData icono;

  static Resultado de(String estado) => switch (estado) {
    'cuadrado' => cuadrado,
    'discrepancia_leve' => leve,
    'cerrado_automatico' => automatico,
    _ => grave,
  };
}

/// GET /caja/estado. El backend decide en qué paso está el flujo; la pantalla
/// no lo deduce, para no desincronizarse con otra pestaña del admin.
@immutable
class EstadoCaja {
  const EstadoCaja({
    required this.hayCajaAbierta,
    this.abierta,
    this.esAtrasada = false,
    this.ventasHastaAhora = 0,
    this.ventasEfectivoHastaAhora = 0,
    this.ventasYapeHastaAhora = 0,
    this.gastosHastaAhora = 0,
    this.ultimoCierreHoy,
    this.turnosHoy = 0,
  });

  factory EstadoCaja.desdeJson(Map<String, dynamic> j) => EstadoCaja(
    hayCajaAbierta: j['hay_caja_abierta'] == true,
    abierta: j['caja_abierta'] is Map<String, dynamic>
        ? Turno.desdeJson(j['caja_abierta'] as Map<String, dynamic>)
        : null,
    esAtrasada: j['es_atrasada'] == true,
    ventasHastaAhora: aDouble(j['ventas_hasta_ahora']),
    ventasEfectivoHastaAhora: aDouble(j['ventas_efectivo_hasta_ahora']),
    ventasYapeHastaAhora: aDouble(j['ventas_yape_hasta_ahora']),
    gastosHastaAhora: aDouble(j['gastos_hasta_ahora']),
    ultimoCierreHoy: j['ultimo_cierre_hoy'] is Map<String, dynamic>
        ? Turno.desdeJson(j['ultimo_cierre_hoy'] as Map<String, dynamic>)
        : null,
    turnosHoy: (j['turnos_hoy'] as num?)?.toInt() ?? 0,
  );

  final bool hayCajaAbierta;
  final Turno? abierta;

  /// El turno abierto es de un día anterior: hay que cerrarlo para abrir otro.
  final bool esAtrasada;

  /// Total vendido (efectivo + Yape), recalculado en cada consulta.
  final double ventasHastaAhora;
  final double ventasEfectivoHastaAhora;
  final double ventasYapeHastaAhora;
  final double gastosHastaAhora;
  final Turno? ultimoCierreHoy;
  final int turnosHoy;
}

/// Opciones de nombre de turno. Es solo una etiqueta para leer el historial.
const nombresTurno = ['Mañana', 'Tarde', 'Noche'];
