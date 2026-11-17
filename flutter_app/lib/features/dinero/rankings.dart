import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/formato.dart';
import '../../design/tema.dart';
import 'modelos.dart';

/// Las listas del dashboard (platos, gastos, salón/mostrador, efectivo/Yape)
/// comparten un mismo formato: puesto, nombre, detalle, monto y una barra
/// proporcional. El dueño aprende a leerlo una vez.

class TopPlatos extends StatelessWidget {
  const TopPlatos({super.key, required this.platos});

  final List<TopPlato> platos;

  @override
  Widget build(BuildContext context) {
    if (platos.isEmpty) return const _SinDatos('Sin ventas en este período.');
    final lista = platos.take(5).toList();
    final mayor = lista.map((p) => p.ingresos).reduce(math.max);
    return Column(
      children: [
        for (final (i, p) in lista.indexed)
          _FilaRanking(
            puesto: i + 1,
            nombre: p.nombre,
            detalle: '${p.cantidad}u',
            monto: p.ingresos,
            proporcion: _proporcion(p.ingresos, mayor),
            color: Colores.de(context).dinero,
          ),
      ],
    );
  }
}

class TopGastos extends StatelessWidget {
  const TopGastos({super.key, required this.gastos});

  final List<TopGasto> gastos;

  @override
  Widget build(BuildContext context) {
    if (gastos.isEmpty) return const _SinDatos('Sin gastos en este período.');
    final lista = gastos.take(3).toList();
    final mayor = lista.map((g) => g.monto).reduce(math.max);
    return Column(
      children: [
        for (final (i, g) in lista.indexed)
          _FilaRanking(
            puesto: i + 1,
            nombre: g.categoria,
            detalle: g.cantidad == 1 ? '1 gasto' : '${g.cantidad} gastos',
            monto: g.monto,
            proporcion: _proporcion(g.monto, mayor),
            color: Colores.de(context).peligro,
          ),
      ],
    );
  }
}

/// Salón contra mostrador, o efectivo contra Yape. Las dos filas se muestran
/// aunque una esté en cero: quien todavía no vendió para llevar tiene que ver
/// el renglón para enterarse de que existe.
class VentasPorTipo extends StatelessWidget {
  const VentasPorTipo({
    super.key,
    required this.filas,
    required this.etiquetas,
  });

  final List<VentaPorTipo> filas;
  final Map<String, String> etiquetas;

  @override
  Widget build(BuildContext context) {
    final total = filas.fold<double>(0, (s, f) => s + f.total);
    if (filas.isEmpty || total == 0) {
      return const _SinDatos('Sin ventas en este período.');
    }
    final mayor = filas.map((f) => f.total).reduce(math.max);
    return Column(
      children: [
        for (final (i, f) in filas.indexed)
          _FilaRanking(
            puesto: i + 1,
            nombre: etiquetas[f.tipo] ?? f.tipo,
            // Sobre el TOTAL y no sobre la fila mayor: la pregunta es "de
            // cada 100 soles, cuántos entran por acá".
            detalle:
                '${f.pedidos} ${f.pedidos == 1 ? 'pedido' : 'pedidos'}'
                ' · ${(f.total / total * 100).round()}%',
            monto: f.total,
            proporcion: _proporcion(f.total, mayor),
            color: Colores.de(context).dinero,
          ),
      ],
    );
  }
}

double _proporcion(double valor, double mayor) =>
    mayor > 0 ? (valor / mayor).clamp(0, 1) : 0;

class _SinDatos extends StatelessWidget {
  const _SinDatos(this.texto);

  final String texto;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: Text(texto, style: TextStyle(color: Colores.de(context).textoSuave)),
  );
}

class _FilaRanking extends StatelessWidget {
  const _FilaRanking({
    required this.puesto,
    required this.nombre,
    required this.detalle,
    required this.monto,
    required this.proporcion,
    required this.color,
  });

  final int puesto;
  final String nombre;
  final String detalle;
  final double monto;
  final double proporcion;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Container(
            width: 28,
            height: 28,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: c.superficieAlt,
              shape: BoxShape.circle,
            ),
            child: Text(
              '$puesto',
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        nombre,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      soles(monto),
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: color,
                        fontFeatures: cifras,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  detalle,
                  style: TextStyle(color: c.textoSuave, fontSize: 12),
                ),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: LinearProgressIndicator(
                    value: proporcion,
                    minHeight: 6,
                    color: color,
                    backgroundColor: c.superficieAlt,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
