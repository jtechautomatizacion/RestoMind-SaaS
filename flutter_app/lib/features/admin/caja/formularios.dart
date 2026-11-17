import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../design/tema.dart';
import 'modelos.dart';

/// Tope del backend (AbrirCajaRequest / CerrarCajaRequest).
const _montoMaximo = 100000.0;

/// null si no es un monto válido. Acepta coma decimal, como se tipea en un
/// celular peruano.
double? _leerMonto(String texto) {
  final v = double.tryParse(texto.trim().replaceAll(',', '.'));
  return v == null || v < 0 || v > _montoMaximo ? null : v;
}

final _soloMontos = FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'));

class _CampoMonto extends StatelessWidget {
  const _CampoMonto({
    required this.controller,
    required this.etiqueta,
    required this.mensajeInvalido,
    this.opcional = false,
  });

  final TextEditingController controller;
  final String etiqueta;
  final String mensajeInvalido;
  final bool opcional;

  @override
  Widget build(BuildContext context) => TextFormField(
    controller: controller,
    keyboardType: const TextInputType.numberWithOptions(decimal: true),
    inputFormatters: [_soloMontos],
    style: const TextStyle(fontFeatures: cifras),
    decoration: InputDecoration(labelText: etiqueta, hintText: '0.00'),
    validator: (v) {
      if (opcional && (v ?? '').trim().isEmpty) return null;
      return _leerMonto(v ?? '') == null ? mensajeInvalido : null;
    },
  );
}

/// Abrir un turno: cuánto hay en la caja al empezar. Siempre disponible
/// mientras no haya otro turno abierto.
class FormAbrirCaja extends StatefulWidget {
  const FormAbrirCaja({super.key, required this.alAbrir});

  final Future<void> Function(double saldoInicial, String? nombreTurno) alAbrir;

  @override
  State<FormAbrirCaja> createState() => _FormAbrirCajaState();
}

class _FormAbrirCajaState extends State<FormAbrirCaja> {
  final _form = GlobalKey<FormState>();
  final _saldo = TextEditingController();
  String? _turno;
  bool _enviando = false;

  @override
  void dispose() {
    _saldo.dispose();
    super.dispose();
  }

  Future<void> _abrir() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _enviando = true);
    try {
      await widget.alAbrir(_leerMonto(_saldo.text)!, _turno);
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _form,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Abrir caja',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 4),
              Text(
                'Escriba cuánto dinero hay en la caja para empezar el turno. '
                'Puede abrir los turnos que necesite en el día.',
                style: TextStyle(color: c.textoSuave),
              ),
              const SizedBox(height: 14),
              _CampoMonto(
                controller: _saldo,
                etiqueta: 'Saldo inicial (S/)',
                mensajeInvalido: 'Escriba un saldo inicial válido',
              ),
              const SizedBox(height: 12),
              Text(
                'Turno (opcional)',
                style: TextStyle(color: c.textoSuave, fontSize: 13),
              ),
              const SizedBox(height: 6),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final nombre in [null, ...nombresTurno])
                    ChoiceChip(
                      label: Text(nombre ?? 'Sin nombre'),
                      selected: _turno == nombre,
                      onSelected: (_) => setState(() => _turno = nombre),
                    ),
                ],
              ),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _enviando ? null : _abrir,
                icon: const Icon(Icons.lock_open),
                label: Text(_enviando ? 'Abriendo…' : 'Abrir caja'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Cerrar el turno: el conteo real contra lo que el sistema espera.
class FormCerrarCaja extends StatefulWidget {
  const FormCerrarCaja({super.key, required this.alCerrar});

  final Future<void> Function(double contado, double retiros, String? razon)
  alCerrar;

  @override
  State<FormCerrarCaja> createState() => _FormCerrarCajaState();
}

class _FormCerrarCajaState extends State<FormCerrarCaja> {
  final _form = GlobalKey<FormState>();
  final _contado = TextEditingController();
  final _retiros = TextEditingController(text: '0');
  final _razon = TextEditingController();
  bool _enviando = false;

  @override
  void dispose() {
    _contado.dispose();
    _retiros.dispose();
    _razon.dispose();
    super.dispose();
  }

  Future<void> _cerrar() async {
    if (!_form.currentState!.validate()) return;
    final razon = _razon.text.trim();
    setState(() => _enviando = true);
    try {
      await widget.alCerrar(
        _leerMonto(_contado.text)!,
        _leerMonto(_retiros.text) ?? 0,
        razon.isEmpty ? null : razon,
      );
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Cerrar caja',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 14),
            _CampoMonto(
              controller: _contado,
              etiqueta: 'Dinero contado en caja ahora (S/)',
              mensajeInvalido: 'Escriba cuánto dinero contó en la caja',
            ),
            const SizedBox(height: 12),
            _CampoMonto(
              controller: _retiros,
              etiqueta: 'Retiros personales del día (S/, opcional)',
              mensajeInvalido: 'Escriba un monto válido',
              opcional: true,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _razon,
              maxLength: 300,
              minLines: 2,
              maxLines: 4,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: '¿Por qué no cuadró? (opcional)',
                hintText: 'Ej.: vuelto mal dado en la mesa 3',
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _enviando ? null : _cerrar,
              icon: const Icon(Icons.fact_check_outlined),
              label: Text(_enviando ? 'Cerrando…' : 'Validar y cerrar caja'),
            ),
          ],
        ),
      ),
    ),
  );
}
