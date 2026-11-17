import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/api/api_error.dart';
import '../../../core/plataforma/plataforma.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'modelos.dart';
import 'repo.dart';

/// Credenciales FIJAS y PÚBLICAS del ambiente BETA de SUNAT, iguales para
/// todos. Se precargan en el restaurante de pruebas para que nadie tenga que
/// buscarlas en la documentación.
const _solBetaUsuario = 'MODDATOS';
const _solBetaClave = 'moddatos';

/// Asistente para activar la facturación por primera vez. Prender el
/// interruptor no alcanza: sin certificado y credenciales SOL el restaurante
/// quedaría "activado" y fallando en CADA cobro.
///
/// Dos pasos porque el primero puede fallar solo (un RUC mal tipeado), y no
/// tiene sentido pedir el certificado de un RUC que todavía no se validó.
/// Devuelve la configuración nueva, o null si se canceló.
Future<Configuracion?> mostrarActivacionSunat(
  BuildContext context, {
  required Configuracion actual,
  required BoletasRepo repo,
}) => mostrarHoja<Configuracion>(
  context,
  (_) => _Activacion(actual: actual, repo: repo),
);

class _Activacion extends StatefulWidget {
  const _Activacion({required this.actual, required this.repo});

  final Configuracion actual;
  final BoletasRepo repo;

  @override
  State<_Activacion> createState() => _ActivacionState();
}

class _ActivacionState extends State<_Activacion> {
  late final _ruc = TextEditingController(text: widget.actual.ruc ?? '');
  late final _razon = TextEditingController(
    text: widget.actual.razonSocial ?? '',
  );
  late final _direccion = TextEditingController(
    text: widget.actual.direccionFiscal ?? '',
  );
  final _claveCert = TextEditingController();
  late final _solUsuario = TextEditingController(
    text: widget.actual.esAmbienteBeta ? _solBetaUsuario : '',
  );
  late final _solClave = TextEditingController(
    text: widget.actual.esAmbienteBeta ? _solBetaClave : '',
  );

  int _paso = 1;
  bool _validado = false;

  /// La razón social vino de un dato oficial (padrón o la que cargó el
  /// superadmin): se muestra de solo lectura para que nadie intente
  /// "corregirla" sin efecto.
  bool _razonOficial = false;
  bool _ocupado = false;
  String? _mensajeRuc;
  String? _error;
  ArchivoElegido? _certificado;

  @override
  void initState() {
    super.initState();
    if (_ruc.text.length == 11) _validarRuc();
  }

  @override
  void dispose() {
    for (final c in [
      _ruc,
      _razon,
      _direccion,
      _claveCert,
      _solUsuario,
      _solClave,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _validarRuc() async {
    final ruc = _ruc.text.trim();
    if (ruc.length != 11) {
      setState(() => _mensajeRuc = 'El RUC tiene 11 dígitos.');
      return;
    }
    // Si el superadmin ya cargó la razón social al dar de alta el
    // restaurante, ese dato es más confiable que el padrón: no se consulta.
    if ((widget.actual.razonSocial ?? '').trim().isNotEmpty) {
      setState(() {
        _validado = true;
        _razonOficial = true;
        _mensajeRuc = 'Datos fiscales ya registrados';
      });
      return;
    }
    setState(() {
      _ocupado = true;
      _mensajeRuc = 'Buscando en el padrón de SUNAT…';
    });
    try {
      final nombre = await widget.repo.razonSocialDelPadron(ruc);
      if (!mounted) return;
      setState(() {
        _validado = true;
        _razonOficial = nombre != null;
        if (nombre != null) _razon.text = nombre;
        // No figurar NO es un callejón sin salida: un RUC recién inscrito, o
        // el 20000000001 de pruebas (ficticio), nunca va a estar.
        _mensajeRuc = nombre != null
            ? 'RUC verificado'
            : 'No figura en el padrón. Escriba la razón social a mano.';
      });
    } on ApiError catch (e) {
      if (mounted) setState(() => _mensajeRuc = e.mensaje);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  void _continuar() {
    if (_razon.text.trim().isEmpty) {
      setState(() => _error = 'Falta la razón social.');
      return;
    }
    if (_direccion.text.trim().isEmpty) {
      setState(() => _error = 'Falta la dirección fiscal.');
      return;
    }
    setState(() {
      _error = null;
      _paso = 2;
    });
  }

  Future<void> _elegirCertificado() async {
    final a = await Servicios.leer(
      context,
    ).plataforma.elegirArchivo(aceptar: '.pfx,.p12');
    if (a != null && mounted) setState(() => _certificado = a);
  }

  Future<void> _vincular() async {
    // Se revisa antes de subir: un formulario incompleto gastaría la subida
    // del certificado para nada.
    final falta = _certificado == null
        ? 'el certificado (.pfx)'
        : _claveCert.text.isEmpty
        ? 'la clave del certificado'
        : _solUsuario.text.trim().isEmpty
        ? 'el usuario SOL'
        : _solClave.text.isEmpty
        ? 'la clave SOL'
        : null;
    if (falta != null) {
      setState(() => _error = 'Falta $falta.');
      return;
    }
    setState(() {
      _ocupado = true;
      _error = null;
    });
    try {
      final cfg = await widget.repo.activarConCertificado(
        ruc: _ruc.text.trim(),
        razonSocial: _razon.text.trim(),
        direccionFiscal: _direccion.text.trim(),
        certificado: _certificado!.bytes,
        nombreCertificado: _certificado!.nombre,
        claveCertificado: _claveCert.text,
        solUsuario: _solUsuario.text.trim(),
        solClave: _solClave.text,
      );
      if (mounted) Navigator.pop(context, cfg);
    } on ApiError catch (e) {
      if (mounted) setState(() => _error = e.mensaje);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Activar boletas electrónicas',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              Pastilla(
                '1 · Datos fiscales',
                tipo: _paso == 1 ? TipoEstado.info : TipoEstado.neutro,
              ),
              Pastilla(
                '2 · Certificado y SOL',
                tipo: _paso == 2 ? TipoEstado.info : TipoEstado.neutro,
              ),
            ],
          ),
          if (widget.actual.esAmbienteBeta) ...[
            const SizedBox(height: 12),
            const Pastilla(
              'Restaurante de pruebas: nada de lo que se emita tiene efecto tributario',
              tipo: TipoEstado.aviso,
              icono: Icons.science_outlined,
            ),
          ],
          const SizedBox(height: 16),
          if (_paso == 1) ..._paso1(c) else ..._paso2(c),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(
              _error!,
              style: TextStyle(color: c.peligro, fontWeight: FontWeight.w600),
            ),
          ],
        ],
      ),
    );
  }

  List<Widget> _paso1(Colores c) => [
    TextField(
      controller: _ruc,
      keyboardType: TextInputType.number,
      inputFormatters: [
        FilteringTextInputFormatter.digitsOnly,
        LengthLimitingTextInputFormatter(11),
      ],
      onChanged: (_) => setState(() {
        _validado = false;
        _razonOficial = false;
      }),
      decoration: InputDecoration(
        labelText: 'RUC del restaurante',
        suffixIcon: IconButton(
          tooltip: 'Validar',
          onPressed: _ocupado ? null : _validarRuc,
          icon: const Icon(Icons.search),
        ),
      ),
      onSubmitted: (_) => _validarRuc(),
    ),
    if (_mensajeRuc != null)
      Padding(
        padding: const EdgeInsets.only(top: 6),
        child: Text(_mensajeRuc!, style: TextStyle(color: c.textoSuave)),
      ),
    if (_validado) ...[
      const SizedBox(height: 14),
      TextField(
        controller: _razon,
        readOnly: _razonOficial,
        decoration: InputDecoration(
          labelText: 'Razón social',
          helperText: _razonOficial ? null : 'Tal como figura en su ficha RUC',
        ),
      ),
      const SizedBox(height: 14),
      TextField(
        controller: _direccion,
        decoration: const InputDecoration(
          labelText: 'Dirección fiscal',
          helperText: 'La que va en el encabezado de cada comprobante',
        ),
      ),
      const SizedBox(height: 18),
      FilledButton(onPressed: _continuar, child: const Text('Continuar')),
    ],
  ];

  List<Widget> _paso2(Colores c) => [
    OutlinedButton.icon(
      onPressed: _ocupado ? null : _elegirCertificado,
      icon: const Icon(Icons.upload_file),
      label: Text(_certificado?.nombre ?? 'Elegir certificado digital (.pfx)'),
    ),
    const SizedBox(height: 14),
    TextField(
      controller: _claveCert,
      obscureText: true,
      decoration: const InputDecoration(labelText: 'Clave del certificado'),
    ),
    const SizedBox(height: 14),
    TextField(
      controller: _solUsuario,
      decoration: const InputDecoration(
        labelText: 'Usuario SOL',
        helperText: 'Sin el RUC adelante',
      ),
    ),
    const SizedBox(height: 14),
    TextField(
      controller: _solClave,
      obscureText: true,
      decoration: const InputDecoration(labelText: 'Clave SOL'),
    ),
    const SizedBox(height: 8),
    Text(
      'El certificado se guarda en el servidor, nunca en la base de datos ni '
      'en este aparato.',
      style: TextStyle(color: c.textoSuave, fontSize: 12),
    ),
    const SizedBox(height: 18),
    Row(
      children: [
        TextButton(
          onPressed: _ocupado ? null : () => setState(() => _paso = 1),
          child: const Text('Atrás'),
        ),
        const Spacer(),
        FilledButton(
          onPressed: _ocupado ? null : _vincular,
          child: Text(_ocupado ? 'Vinculando…' : 'Vincular con SUNAT'),
        ),
      ],
    ),
  ];
}
