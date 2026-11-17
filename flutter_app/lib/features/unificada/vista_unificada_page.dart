import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../core/servicios.dart';
import '../../design/widgets.dart';
import '../../shell/shell.dart';
import '../mesas/acciones.dart';
import '../mesas/sala.dart';
import 'columnas.dart';

/// "Atiendo solo": las tres etapas de una mesa —tomar el pedido, cocinarlo y
/// cobrarlo— en una sola pantalla, para quien atiende sin ayuda. Con
/// pestañas separadas saltaría Mesas → Cocina → Mesas por cada cliente,
/// perdiendo de vista lo que estaba haciendo.
///
/// Reusa las hojas de pedido y de cobro de Mesas: duplicar el flujo de cobro
/// sería tener dos versiones de la lógica de dinero.
///
/// Los atajos de teclado solo NAVEGAN (tipear un número abre esa mesa).
/// Ninguno cobra: cobrar mueve plata y libera la mesa, y que lo dispare una
/// tecla que se aprieta sin mirar (Enter) es un cobro equivocado esperando.
class VistaUnificadaPage extends StatefulWidget {
  const VistaUnificadaPage({super.key, required this.sala});

  final Sala sala;

  @override
  State<VistaUnificadaPage> createState() => _VistaUnificadaPageState();
}

class _VistaUnificadaPageState extends State<VistaUnificadaPage> {
  /// Ventana para juntar dígitos: tipear "12" sin saltar antes a la mesa 1.
  static const _ventanaTeclado = Duration(milliseconds: 700);

  String _tecleado = '';
  Timer? _reloj;

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_alTeclear);
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_alTeclear);
    _reloj?.cancel();
    super.dispose();
  }

  bool _alTeclear(KeyEvent e) {
    if (e is! KeyDownEvent) return false;
    final k = HardwareKeyboard.instance;
    if (k.isControlPressed || k.isAltPressed || k.isMetaPressed) return false;
    // Con una hoja o un diálogo abierto la tarea es esa: saltar de mesa
    // perdería un pedido a medio armar.
    if (ModalRoute.isCurrentOf(context) != true) return false;
    // Escribiendo en un campo, las teclas son texto y no atajos.
    if (FocusManager.instance.primaryFocus?.context?.widget is EditableText) {
      return false;
    }
    final ch = e.character;
    if (ch == null || !RegExp(r'^[0-9]$').hasMatch(ch)) return false;
    _tecleado += ch;
    _reloj?.cancel();
    _reloj = Timer(_ventanaTeclado, _abrirTecleada);
    return true;
  }

  void _abrirTecleada() {
    final numero = int.parse(_tecleado);
    _tecleado = '';
    if (!mounted) return;
    final mesa = widget.sala.mesas.where((m) => m.numero == numero).firstOrNull;
    if (mesa == null) {
      avisar(context, 'No hay mesa $numero.');
      return;
    }
    unawaited(abrirMesa(context, widget.sala, mesa));
  }

  @override
  Widget build(BuildContext context) {
    final sala = widget.sala;
    final esAdmin = Servicios.de(context).sesion.usuario!.esAdmin;
    final porCobrar = sala.porCobrar;
    final ocupadas = sala.mesas.where((m) => m.ocupada).length;
    final mesas = ColumnaMesas(sala: sala);
    final cocina = ColumnaCocina(sala: sala);
    final cobro = ColumnaPorCobrar(sala: sala, porCobrar: porCobrar);
    return Column(
      children: [
        Expanded(
          child: LayoutBuilder(
            builder: (context, medidas) => medidas.maxWidth >= 900
                ? Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        flex: 5,
                        child: Columna(titulo: '1 · Mesas', child: mesas),
                      ),
                      Expanded(
                        flex: 3,
                        child: Columna(titulo: '2 · En cocina', child: cocina),
                      ),
                      Expanded(
                        flex: 3,
                        child: Columna(
                          titulo: '3 · Esperando la cuenta',
                          child: cobro,
                        ),
                      ),
                    ],
                  )
                // En pantallas chicas las columnas pasan a pestañas: mismo
                // contenido, solo se oculta lo que no está en foco.
                : DefaultTabController(
                    length: 3,
                    child: Column(
                      children: [
                        TabBar(
                          tabs: [
                            _Pestana('Mesas', ocupadas),
                            _Pestana('Cocina', sala.cocina.length),
                            _Pestana('Cobrar', porCobrar.length),
                          ],
                        ),
                        Expanded(
                          child: TabBarView(children: [mesas, cocina, cobro]),
                        ),
                      ],
                    ),
                  ),
          ),
        ),
        PieUnificado(
          sala: sala,
          porCobrar: porCobrar,
          verVendido: esAdmin,
          cajaGate: ShellScope.de(context).cajaGate,
        ),
      ],
    );
  }
}

class _Pestana extends StatelessWidget {
  const _Pestana(this.texto, this.cuenta);

  final String texto;
  final int cuenta;

  @override
  Widget build(BuildContext context) => Tab(
    child: Badge.count(
      count: cuenta,
      isLabelVisible: cuenta > 0,
      offset: const Offset(14, -6),
      child: Text(texto),
    ),
  );
}
