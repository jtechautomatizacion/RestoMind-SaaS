import 'package:flutter/material.dart';

import '../../core/formato.dart';
import '../../design/widgets.dart';
import 'modelos.dart';

/// Atajos de 7, 14 y 30 días, o un rango Desde/Hasta que se aplica recién con
/// "Aplicar" (elegir la primera fecha no dispara una consulta a medias).
class SelectorPeriodo extends StatefulWidget {
  const SelectorPeriodo({
    super.key,
    required this.periodo,
    required this.alCambiar,
  });

  final Periodo periodo;
  final ValueChanged<Periodo> alCambiar;

  @override
  State<SelectorPeriodo> createState() => _SelectorPeriodoState();
}

class _SelectorPeriodoState extends State<SelectorPeriodo> {
  late DateTime _desde;
  late DateTime _hasta;

  DateTime get _hoy => DateTime.now();

  void _sincronizar() {
    final (desde, hasta) = widget.periodo.fechas(_hoy);
    _desde = desde;
    _hasta = hasta;
  }

  @override
  void initState() {
    super.initState();
    _sincronizar();
  }

  @override
  void didUpdateWidget(SelectorPeriodo old) {
    super.didUpdateWidget(old);
    // Al tocar un atajo, las fechas pasan a mostrar ese mismo período.
    if (old.periodo != widget.periodo) _sincronizar();
  }

  Future<void> _elegir({required bool desde}) async {
    final elegida = await showDatePicker(
      context: context,
      initialDate: desde ? _desde : _hasta,
      firstDate: DateTime(2020),
      lastDate: _hoy,
      helpText: desde ? 'Desde' : 'Hasta',
    );
    if (elegida == null || !mounted) return;
    setState(() => desde ? _desde = elegida : _hasta = elegida);
  }

  void _aplicar() {
    final error = validarRango(_desde, _hasta);
    if (error != null) {
      avisar(context, error);
      return;
    }
    widget.alCambiar(Periodo.rango(_desde, _hasta));
  }

  @override
  Widget build(BuildContext context) {
    final dias = widget.periodo.dias;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final d in diasRapidos)
              ChoiceChip(
                label: Text('$d días'),
                selected: dias == d,
                onSelected: (_) => widget.alCambiar(Periodo.ultimos(d)),
              ),
          ],
        ),
        const SizedBox(height: 12),
        LayoutBuilder(
          builder: (context, caja) {
            final fechas = [
              Expanded(
                child: _CampoFecha(
                  etiqueta: 'Desde',
                  valor: _desde,
                  alTocar: () => _elegir(desde: true),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _CampoFecha(
                  etiqueta: 'Hasta',
                  valor: _hasta,
                  alTocar: () => _elegir(desde: false),
                ),
              ),
            ];
            final aplicar = FilledButton(
              onPressed: _aplicar,
              child: const Text('Aplicar'),
            );
            // En un celular el botón baja a su propia fila: al lado de las
            // dos fechas las dejaba cortadas ("11/11/202").
            if (caja.maxWidth < 520) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(children: fechas),
                  const SizedBox(height: 8),
                  aplicar,
                ],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [...fechas, const SizedBox(width: 8), aplicar],
            );
          },
        ),
      ],
    );
  }
}

class _CampoFecha extends StatelessWidget {
  const _CampoFecha({
    required this.etiqueta,
    required this.valor,
    required this.alTocar,
  });

  final String etiqueta;
  final DateTime valor;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: alTocar,
    borderRadius: BorderRadius.circular(12),
    child: InputDecorator(
      decoration: InputDecoration(
        labelText: etiqueta,
        suffixIcon: const Icon(Icons.calendar_today_outlined, size: 18),
      ),
      child: Text(fecha(valor), softWrap: false),
    ),
  );
}
