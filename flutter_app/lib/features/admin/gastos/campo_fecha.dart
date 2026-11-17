import 'package:flutter/material.dart';

import '../../../core/formato.dart';

/// Fecha de calendario para un formulario. El selector no ofrece días
/// futuros: ni un gasto ni un movimiento de stock pueden ser de mañana.
class CampoFecha extends StatelessWidget {
  const CampoFecha({
    super.key,
    required this.valor,
    required this.cambiar,
    this.error,
  });

  final DateTime valor;
  final ValueChanged<DateTime> cambiar;
  final String? error;

  Future<void> _elegir(BuildContext context) async {
    final hoy = DateTime.now();
    final ultimo = DateTime(hoy.year, hoy.month, hoy.day);
    final elegida = await showDatePicker(
      context: context,
      initialDate: valor.isAfter(ultimo) ? ultimo : valor,
      firstDate: DateTime(2020),
      lastDate: ultimo,
    );
    if (elegida != null) cambiar(elegida);
  }

  @override
  Widget build(BuildContext context) => InkWell(
    borderRadius: BorderRadius.circular(12),
    onTap: () => _elegir(context),
    child: InputDecorator(
      decoration: InputDecoration(
        labelText: 'Fecha',
        errorText: error,
        suffixIcon: const Icon(Icons.calendar_today_outlined),
      ),
      child: Text(fecha(valor)),
    ),
  );
}
