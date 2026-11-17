import 'package:flutter/material.dart';

import '../../../core/formato.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'modelos.dart';
import 'reporte_cierre.dart';

/// Franja de color con el estado de la caja: lo primero que se lee.
class BannerCaja extends StatelessWidget {
  const BannerCaja({
    super.key,
    required this.tipo,
    required this.icono,
    required this.titulo,
    this.subtitulo,
  });

  final TipoEstado tipo;
  final IconData icono;
  final String titulo;
  final String? subtitulo;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final esquema = Theme.of(context).colorScheme;
    final (fondo, frente) = switch (tipo) {
      TipoEstado.exito => (c.exitoFondo, c.exito),
      TipoEstado.aviso => (c.avisoFondo, c.aviso),
      TipoEstado.peligro => (c.peligroFondo, c.peligro),
      TipoEstado.info => (esquema.secondaryContainer, esquema.primary),
      TipoEstado.neutro => (c.superficieAlt, c.textoSuave),
    };
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: fondo,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icono, color: frente, size: 30),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  titulo,
                  style: TextStyle(
                    color: frente,
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (subtitulo != null)
                  Text(subtitulo!, style: TextStyle(color: c.texto)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Turno abierto: lo vendido y gastado hasta este momento, recalculado por el
/// backend en cada consulta.
class TurnoAbiertoCard extends StatelessWidget {
  const TurnoAbiertoCard({super.key, required this.estado});

  final EstadoCaja estado;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final t = estado.abierta!;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            BannerCaja(
              tipo: TipoEstado.exito,
              icono: Icons.lock_open,
              titulo: t.nombreTurno == null
                  ? 'Caja abierta'
                  : 'Turno ${t.nombreTurno}',
              subtitulo: 'Desde ${fechaHora(t.abiertoEn)}',
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: Indicador(
                    etiqueta: 'Ventas hasta ahora',
                    valor: soles(estado.ventasHastaAhora),
                    color: c.dinero,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Indicador(
                    etiqueta: 'Gastos hasta ahora',
                    valor: soles(estado.gastosHastaAhora),
                    color: c.peligro,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            // Dice explícitamente que el Yape NO entra al conteo: sin esa
            // línea, el dueño lo suma a mano para "corregir" el esperado.
            FilaMonto(
              'Efectivo (esto se cuenta en la caja)',
              soles(estado.ventasEfectivoHastaAhora),
              color: c.dinero,
            ),
            FilaMonto(
              'Yape/Plin (no entra al conteo)',
              soles(estado.ventasYapeHastaAhora),
            ),
            if (estado.esAtrasada) ...[
              const SizedBox(height: 8),
              const BannerCaja(
                tipo: TipoEstado.aviso,
                icono: Icons.history,
                titulo: 'Turno de un día anterior',
                subtitulo:
                    'Quedó abierto sin cerrar. Ciérrelo para poder abrir uno '
                    'nuevo.',
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// El último turno cerrado hoy. Solo informa: nunca impide abrir otro.
class UltimoCierreCard extends StatelessWidget {
  const UltimoCierreCard({
    super.key,
    required this.turno,
    required this.turnosHoy,
    required this.alImprimir,
  });

  final Turno turno;
  final int turnosHoy;
  final VoidCallback alImprimir;

  @override
  Widget build(BuildContext context) {
    final r = turno.resultado;
    // Con nombre, "Turno Mañana" dice más que "Turno 2 de hoy".
    final cual = turno.nombreTurno != null
        ? ' · Turno ${turno.nombreTurno}'
        : turnosHoy > 1
        ? ' · Turno $turnosHoy de hoy'
        : '';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            BannerCaja(
              tipo: r.tipo,
              icono: r.icono,
              titulo: r.titulo,
              subtitulo: 'Cerrado hoy a las ${hora(turno.cerradoEn)}$cual',
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: Indicador(
                    etiqueta: 'Esperado',
                    valor: soles(turno.saldoEsperado),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Indicador(
                    etiqueta: 'Contado',
                    valor: soles(turno.saldoContado),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: alImprimir,
              icon: const Icon(Icons.print_outlined),
              label: const Text('Ver / imprimir reporte'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Cierres pasados, el más reciente primero, cada uno reimprimible.
/// [turnos] null = no se pudo cargar.
class HistorialCaja extends StatelessWidget {
  const HistorialCaja({
    super.key,
    required this.turnos,
    required this.alImprimir,
  });

  final List<Turno>? turnos;
  final ValueChanged<Turno> alImprimir;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final lista = turnos;
    if (lista == null || lista.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 12),
        child: Text(
          lista == null
              ? 'No se pudo cargar el historial.'
              : 'Sin cierres registrados todavía.',
          style: TextStyle(color: c.textoSuave),
        ),
      );
    }
    return Card(
      child: Column(
        children: [
          for (final (i, t) in lista.indexed) ...[
            if (i > 0) const Divider(),
            _FilaHistorial(turno: t, alImprimir: () => alImprimir(t)),
          ],
        ],
      ),
    );
  }
}

class _FilaHistorial extends StatelessWidget {
  const _FilaHistorial({required this.turno, required this.alImprimir});

  final Turno turno;
  final VoidCallback alImprimir;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final r = turno.resultado;
    final color = switch (r.tipo) {
      TipoEstado.exito => c.exito,
      TipoEstado.peligro => c.peligro,
      _ => c.aviso,
    };
    // La hora de cierre, no solo la fecha: con varios turnos el mismo día, la
    // fecha sola no los distingue.
    final titulo = [
      fecha(DateTime.tryParse(turno.fecha)),
      if (turno.cerradoEn != null) hora(turno.cerradoEn),
      ?turno.nombreTurno,
    ].join(' · ');
    return ListTile(
      leading: Icon(r.icono, color: color),
      title: Text(titulo, style: const TextStyle(fontWeight: FontWeight.w700)),
      subtitle: Text(
        '${r.titulo} · ${conSigno(turno.diferencia)}',
        style: const TextStyle(fontFeatures: cifras),
      ),
      trailing: IconButton(
        tooltip: 'Ver / imprimir reporte',
        onPressed: alImprimir,
        icon: const Icon(Icons.print_outlined),
      ),
    );
  }
}
