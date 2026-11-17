import 'package:flutter/material.dart';

import '../../core/servicios.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';
import '../unificada/vista_unificada_page.dart';
import 'acciones.dart';
import 'gestion_mesas.dart';
import 'mesa_tarjeta.dart';
import 'repo.dart';
import 'sala.dart';

/// Pestaña Mesas: tocar una mesa libre abre un pedido nuevo; una ocupada
/// abre su cuenta (agregar pedido o cobrar).
class MesasPage extends StatefulWidget {
  const MesasPage({super.key});

  @override
  State<MesasPage> createState() => _MesasPageState();
}

class _MesasPageState extends State<MesasPage> {
  /// Por APARATO y no por cuenta: el mismo dueño puede atender solo desde el
  /// celular y tener la tablet del mostrador "en equipo".
  static const _claveVista = 'vista_unificada';

  late final Servicios _s = Servicios.leer(context);
  late bool _unificada =
      _s.sesion.usuario!.vistaUnificada &&
      _s.plataforma.preferencia(_claveVista) == '1';
  late final Sala _sala = Sala(
    MesasRepo(_s.api),
    unificada: _unificada,
    esAdmin: _s.sesion.usuario!.esAdmin,
    conCarta: !_s.sesion.usuario!.esSoloCobra,
  )..iniciar();

  @override
  void dispose() {
    _sala.dispose();
    super.dispose();
  }

  void _cambiarVista(bool unificada) {
    setState(() => _unificada = unificada);
    _s.plataforma.guardarPreferencia(_claveVista, unificada ? '1' : '0');
    _sala.unificada = unificada;
  }

  @override
  Widget build(BuildContext context) {
    final usuario = _s.sesion.usuario!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _Barra(
          verInterruptor: usuario.vistaUnificada,
          unificada: _unificada,
          alCambiar: _cambiarVista,
          alGestionar: usuario.esAdmin
              ? () => abrirGestionMesas(context, _sala)
              : null,
        ),
        Expanded(
          child: ListenableBuilder(
            listenable: _sala,
            builder: (context, _) {
              if (!_sala.cargada) {
                final error = _sala.error;
                return error == null
                    ? const Center(child: CircularProgressIndicator())
                    : ErrorCarga(error: error, reintentar: _sala.refrescar);
              }
              return _unificada
                  ? VistaUnificadaPage(sala: _sala)
                  : _GrillaMesas(sala: _sala);
            },
          ),
        ),
      ],
    );
  }
}

class _Barra extends StatelessWidget {
  const _Barra({
    required this.verInterruptor,
    required this.unificada,
    required this.alCambiar,
    required this.alGestionar,
  });

  final bool verInterruptor;
  final bool unificada;
  final ValueChanged<bool> alCambiar;
  final VoidCallback? alGestionar;

  @override
  Widget build(BuildContext context) {
    if (!verInterruptor && alGestionar == null) return const SizedBox.shrink();
    final c = Colores.de(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 12,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              // Los nombres dicen QUIÉN está trabajando, no la forma de la
              // pantalla: la pregunta real es "¿hay alguien más en el turno?".
              if (verInterruptor)
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(
                      value: false,
                      icon: Icon(Icons.groups_outlined),
                      label: Text('En equipo'),
                    ),
                    ButtonSegment(
                      value: true,
                      icon: Icon(Icons.person_outline),
                      label: Text('Atiendo solo'),
                    ),
                  ],
                  selected: {unificada},
                  onSelectionChanged: (v) => alCambiar(v.first),
                ),
              if (alGestionar != null)
                OutlinedButton.icon(
                  onPressed: alGestionar,
                  icon: const Icon(Icons.edit_outlined),
                  label: const Text('Gestionar mesas'),
                ),
            ],
          ),
          if (verInterruptor)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                unificada
                    ? 'Mesas, cocina y cobro juntos en una pantalla. Para cuando está sin ayuda.'
                    : 'Cada uno en su pantalla: quien atiende toma pedidos, cocina cocina, caja cobra.',
                style: TextStyle(color: c.textoSuave, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }
}

/// La grilla de siempre ("En equipo").
class _GrillaMesas extends StatelessWidget {
  const _GrillaMesas({required this.sala});

  final Sala sala;

  @override
  Widget build(BuildContext context) {
    final soloCobra = Servicios.de(context).sesion.usuario!.esSoloCobra;
    final c = Colores.de(context);
    return RefreshIndicator(
      onRefresh: sala.refrescar,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          // Sin mesas igual se muestra "Para llevar": un local que vende solo
          // en el mostrador, o que no cargó sus mesas, tiene que poder vender.
          if (sala.mesas.isEmpty)
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              sliver: SliverToBoxAdapter(
                child: Text(
                  'Aún no hay mesas configuradas.',
                  style: TextStyle(color: c.textoSuave),
                ),
              ),
            ),
          SliverPadding(
            padding: const EdgeInsets.all(16),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 150,
                mainAxisExtent: 168,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
              ),
              delegate: SliverChildListDelegate([
                for (final m in sala.mesas)
                  TarjetaMesa(
                    mesa: m,
                    estado: sala.estadoDe(m),
                    // Quien solo cobra ve las mesas libres apagadas: tocarlas
                    // no le sirve y confundiría cobrar con tomar un pedido.
                    onTap: soloCobra && !m.ocupada
                        ? null
                        : () => abrirMesa(context, sala, m),
                  ),
                if (!soloCobra)
                  TarjetaParaLlevar(onTap: () => abrirPedido(context, sala)),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}
