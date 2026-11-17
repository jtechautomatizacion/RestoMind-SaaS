import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/api/api_error.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';
import 'documento.dart';
import 'repo.dart';

/// Desde S/ 700 SUNAT exige identificar al comprador en una boleta.
const topePublicoGeneral = 700.0;

enum _Via { sinDoc, ruc, dni }

/// A nombre de quién va el comprobante, y el botón que cobra.
///
/// Sin facturación activa no hay tres caminos sino uno: el DNI/RUC del
/// comensal solo existe para ponerlo en un comprobante, así que pedirlo sería
/// hacerle perder tiempo al cajero por un dato que no va a ningún lado. Las
/// pestañas se OCULTAN (no se apagan: una pestaña gris invita a preguntarse
/// qué falta para habilitarla) y queda solo Cobrar.
///
/// Con facturación, el cajero ELIGE antes de tipear, así ve de entrada qué
/// comprobante va a salir en vez de descubrirlo con el número ya puesto.
class PanelDocumento extends StatefulWidget {
  const PanelDocumento({
    super.key,
    required this.repo,
    required this.total,
    required this.emite,
    required this.emiteFacturas,
    required this.ocupado,
    required this.alCobrar,
  });

  final MesasRepo repo;
  final double total;

  /// ¿El restaurante emite comprobantes? (usuario.usarSunat)
  final bool emite;

  /// ¿Puede facturar? En Nuevo RUS un RUC recibe BOLETA con su RUC.
  final bool emiteFacturas;
  final bool ocupado;

  /// (documento, nombre). Vacío = Público General.
  final void Function(String documento, String nombre) alCobrar;

  @override
  State<PanelDocumento> createState() => _PanelDocumentoState();
}

class _PanelDocumentoState extends State<PanelDocumento> {
  _Via _via = _Via.sinDoc;
  final _ruc = _Documento(11);
  final _dni = _Documento(8);

  @override
  void dispose() {
    _ruc.dispose();
    _dni.dispose();
    super.dispose();
  }

  void _alTipear(_Via via, _Documento d, String valor) {
    d.espera?.cancel();
    setState(() {
      d.resultado = false;
      d.info = null;
    });
    if (valor.length != d.largo) return;
    // Un RUC mal tipeado se atrapa acá sin gastar consulta. Un DNI no tiene
    // dígito de control: solo se revisa el largo.
    if (via == _Via.ruc && !digitoRucValido(valor)) {
      setState(
        () => d.info = (
          'Revise el número, no parece un RUC válido.',
          TipoEstado.aviso,
        ),
      );
      return;
    }
    setState(() => d.info = ('Buscando...', TipoEstado.neutro));
    // Se espera a que deje de escribir: la consulta tiene cuota por IP.
    d.espera = Timer(
      const Duration(milliseconds: 350),
      () => _consultar(via, d, valor),
    );
  }

  Future<void> _consultar(_Via via, _Documento d, String numero) async {
    final esRuc = via == _Via.ruc;
    var sinPadron = false;
    String? nombre;
    String? advertencia;
    var encontrado = false;
    try {
      final r = await widget.repo.consultarDocumento(numero);
      encontrado = r.encontrado;
      nombre = r.nombre;
      advertencia = r.advertencia;
    } on ApiError catch (e) {
      // 503 = el padrón no está instalado en el servidor. No frena el cobro,
      // pero se dice: sin explicación el nombre vacío parece un bug.
      sinPadron = e.status == 503;
    }
    // Si siguió tipeando mientras la consulta viajaba, ya no corresponde.
    if (!mounted || d.numero.text != numero) return;
    setState(() {
      if (encontrado) {
        d.nombre.text = nombre ?? '';
        // Fijo cuando el dato es oficial (padrón): editable invitaría a
        // "corregirlo" creyendo que eso cambia algo.
        d.nombreFijo = esRuc;
        d.info = advertencia != null
            ? (advertencia, TipoEstado.aviso)
            : ('Verificado', TipoEstado.exito);
      } else {
        d.nombre.clear();
        d.nombreFijo = false;
        d.info = (
          sinPadron
              ? 'El padrón de SUNAT no está instalado. Escriba el nombre a mano.'
              : esRuc
              ? 'No figura en el padrón. Escriba la razón social.'
              : 'No lo tenemos registrado. Escriba el nombre.',
          TipoEstado.neutro,
        );
      }
      d.resultado = true;
    });
  }

  void _revisar(_Documento d) => setState(() {
    d.espera?.cancel();
    d.numero.clear();
    d.nombre.clear();
    d.nombreFijo = false;
    d.resultado = false;
    d.info = null;
  });

  void _cobrarCon(_Via via) {
    if (via == _Via.sinDoc) {
      widget.alCobrar('', '');
      return;
    }
    final d = via == _Via.ruc ? _ruc : _dni;
    final documento = d.numero.text.trim();
    final nombre = d.nombre.text.trim();
    if (documento.isEmpty) {
      avisar(context, via == _Via.ruc ? 'Falta el RUC.' : 'Falta el DNI.');
      return;
    }
    // SUNAT no acepta un RUC sin razón social. Con DNI el nombre es opcional.
    if (via == _Via.ruc && nombre.isEmpty) {
      avisar(context, 'Falta la razón social.');
      return;
    }
    widget.alCobrar(documento, nombre);
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.emite) {
      return _BotonCobrar(
        texto: 'Cobrar',
        onPressed: widget.ocupado ? null : () => _cobrarCon(_Via.sinDoc),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SegmentedButton<_Via>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: _Via.sinDoc, label: Text('Sin documento')),
            ButtonSegment(value: _Via.ruc, label: Text('Con RUC')),
            ButtonSegment(value: _Via.dni, label: Text('Con DNI')),
          ],
          selected: {_via},
          onSelectionChanged: (v) => setState(() => _via = v.first),
        ),
        const SizedBox(height: 12),
        switch (_via) {
          _Via.sinDoc => _sinDocumento(),
          _Via.ruc => _conDocumento(_Via.ruc, _ruc),
          _Via.dni => _conDocumento(_Via.dni, _dni),
        },
      ],
    );
  }

  Widget _sinDocumento() {
    final c = Colores.de(context);
    // El tope lo impone SUNAT. Avisarlo ANTES de cobrar deja pedir el
    // documento con el cliente todavía enfrente.
    final superaTope = widget.total >= topePublicoGeneral;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // "Sin documento" NO es "sin comprobante": igual sale boleta, a
        // nombre de Público General.
        Text(
          'Se emite boleta a Público General, sin identificar al cliente.',
          style: TextStyle(color: c.textoSuave, fontSize: 13),
        ),
        if (superaTope) ...[
          const SizedBox(height: 8),
          const AvisoAmbar(
            'Desde S/ 700 SUNAT exige identificar al cliente. '
            'Pídale el DNI o el RUC en las otras pestañas.',
          ),
        ],
        const SizedBox(height: 10),
        _BotonCobrar(
          texto: 'Cobrar',
          onPressed: widget.ocupado || superaTope
              ? null
              : () => _cobrarCon(_Via.sinDoc),
        ),
      ],
    );
  }

  Widget _conDocumento(_Via via, _Documento d) {
    final c = Colores.de(context);
    final esRuc = via == _Via.ruc;
    final info = d.info;
    final chip = widget.emiteFacturas
        ? ('Factura · F001', TipoEstado.info)
        : ('Boleta · RUC del comprador', TipoEstado.neutro);
    return Column(
      key: ValueKey(via),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: d.numero,
          autofocus: true,
          keyboardType: TextInputType.number,
          inputFormatters: [
            FilteringTextInputFormatter.digitsOnly,
            LengthLimitingTextInputFormatter(d.largo),
          ],
          decoration: InputDecoration(
            labelText: esRuc ? 'RUC (11 dígitos)' : 'DNI (8 dígitos)',
          ),
          onChanged: (v) => _alTipear(via, d, v),
        ),
        if (info != null)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Pastilla(info.$1, tipo: info.$2),
            ),
          ),
        if (d.resultado) ...[
          const SizedBox(height: 12),
          // Qué comprobante va a salir, dicho ANTES de cobrar: un RUC produce
          // factura solo si el restaurante puede emitirlas (Nuevo RUS no).
          if (esRuc)
            Align(
              alignment: Alignment.centerLeft,
              child: Pastilla(chip.$1, tipo: chip.$2),
            ),
          if (esRuc) const SizedBox(height: 10),
          TextField(
            controller: d.nombre,
            readOnly: d.nombreFijo,
            maxLength: 200,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(
              labelText: esRuc ? 'Empresa' : 'Nombre del cliente',
              counterText: '',
              fillColor: d.nombreFijo ? c.superficieAlt : null,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _BotonCobrar(
                  texto: esRuc ? 'Sí, cobrar' : 'Cobrar',
                  onPressed: widget.ocupado ? null : () => _cobrarCon(via),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: () => _revisar(d),
                child: const Text('Revisar'),
              ),
            ],
          ),
        ],
      ],
    );
  }
}

class _Documento {
  _Documento(this.largo);

  final int largo;
  final numero = TextEditingController();
  final nombre = TextEditingController();
  Timer? espera;
  (String, TipoEstado)? info;
  bool resultado = false;
  bool nombreFijo = false;

  void dispose() {
    espera?.cancel();
    numero.dispose();
    nombre.dispose();
  }
}

class _BotonCobrar extends StatelessWidget {
  const _BotonCobrar({required this.texto, required this.onPressed});

  final String texto;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return FilledButton.icon(
      style: FilledButton.styleFrom(
        backgroundColor: c.exito,
        foregroundColor: c.sobreSemantico,
      ),
      onPressed: onPressed,
      icon: const Icon(Icons.point_of_sale),
      label: Text(texto),
    );
  }
}

/// Aviso en ámbar dentro del cobro.
class AvisoAmbar extends StatelessWidget {
  const AvisoAmbar(this.texto, {super.key});

  final String texto;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: c.avisoFondo,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 18, color: c.aviso),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              texto,
              style: TextStyle(color: c.aviso, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
