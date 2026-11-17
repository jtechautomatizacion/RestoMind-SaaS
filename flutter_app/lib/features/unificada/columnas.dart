import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/formato.dart';
import '../../design/papel.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';
import '../../shell/caja_gate.dart';
import '../mesas/acciones.dart';
import '../mesas/mesa_tarjeta.dart';
import '../mesas/modelos.dart';
import '../mesas/sala.dart';

/// Una columna de "Atiendo solo" en pantalla ancha.
class Columna extends StatelessWidget {
  const Columna({super.key, required this.titulo, required this.child});

  final String titulo;
  final Widget child;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      border: Border(right: BorderSide(color: Colores.de(context).borde)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
          child: TituloSeccion(titulo),
        ),
        Expanded(child: child),
      ],
    ),
  );
}

class _TextoVacio extends StatelessWidget {
  const _TextoVacio(this.texto);

  final String texto;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(24),
    child: Text(
      texto,
      textAlign: TextAlign.center,
      style: TextStyle(color: Colores.de(context).textoSuave),
    ),
  );
}

class ColumnaMesas extends StatelessWidget {
  const ColumnaMesas({super.key, required this.sala});

  final Sala sala;

  @override
  Widget build(BuildContext context) {
    final minutos = sala.minutosPorMesa(DateTime.now());
    return CustomScrollView(
      slivers: [
        if (sala.mesas.isEmpty)
          const SliverToBoxAdapter(
            child: _TextoVacio('Aún no hay mesas configuradas.'),
          ),
        SliverPadding(
          padding: const EdgeInsets.all(12),
          sliver: SliverGrid(
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 130,
              mainAxisExtent: 168,
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
            ),
            delegate: SliverChildListDelegate([
              for (final m in sala.mesas)
                TarjetaMesa(
                  mesa: m,
                  estado: sala.estadoDe(m),
                  minutos: m.ocupada ? minutos[m.numero] : null,
                  onTap: () => abrirMesa(context, sala, m),
                ),
              // Quien atiende solo es justo el que cobra en el mostrador:
              // tener que cambiar de vista para vender para llevar sería lo
              // contrario de por qué existe esta pantalla.
              TarjetaParaLlevar(onTap: () => abrirPedido(context, sala)),
            ]),
          ),
        ),
      ],
    );
  }
}

class ColumnaCocina extends StatelessWidget {
  const ColumnaCocina({super.key, required this.sala});

  final Sala sala;

  @override
  Widget build(BuildContext context) {
    if (sala.cocina.isEmpty) {
      return const _TextoVacio('Nada en cocina ahora mismo.');
    }
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        for (final c in sala.cocina)
          _TarjetaCocina(key: ValueKey(c.id), comanda: c, sala: sala),
      ],
    );
  }
}

class _TarjetaCocina extends StatefulWidget {
  const _TarjetaCocina({super.key, required this.comanda, required this.sala});

  final ComandaCocina comanda;
  final Sala sala;

  @override
  State<_TarjetaCocina> createState() => _TarjetaCocinaState();
}

class _TarjetaCocinaState extends State<_TarjetaCocina> {
  bool _enviando = false;

  Future<void> _listo() async {
    setState(() => _enviando = true);
    try {
      await widget.sala.repo.marcarEntregada(widget.comanda.id);
      if (mounted) avisar(context, 'Comanda entregada', tipo: TipoAviso.exito);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    }
    // Se pregunta al servidor en vez de dar por hecho el resultado: si falló,
    // la tarjeta sigue; si salió, la mesa pasa a "Esperando la cuenta" ya,
    // sin esperar la próxima vuelta del reloj.
    await widget.sala.refrescar();
    if (mounted) setState(() => _enviando = false);
  }

  @override
  Widget build(BuildContext context) {
    final papel = Papel.de(context);
    final comanda = widget.comanda;
    // Mismo umbral que la pantalla de Cocina: desde los 15 minutos, demora.
    final tarde = comanda.minutos >= minutosAlerta;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TiraDePapel(
        marca: tarde ? papel.peligro : null,
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              rotuloPedido(comanda.numeroMesa, comanda.id),
              style: impreso(tamano: 20),
            ),
            const Corte(),
            for (final p in comanda.platos)
              Text('${p.cantidad} x ${p.nombre}', style: impreso(tamano: 14)),
            const Corte(),
            CronometroComanda(
              minutos: comanda.minutos,
              atrasada: tarde,
              limite: minutosAlerta,
            ),
            const SizedBox(height: 10),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: papel.exito,
                foregroundColor: Colors.white,
                disabledBackgroundColor: papel.corte,
              ),
              onPressed: _enviando ? null : _listo,
              icon: const Icon(Icons.check),
              label: const Text('Está listo'),
            ),
          ],
        ),
      ),
    );
  }
}

class ColumnaPorCobrar extends StatelessWidget {
  const ColumnaPorCobrar({
    super.key,
    required this.sala,
    required this.porCobrar,
  });

  final Sala sala;
  final List<PorCobrar> porCobrar;

  void _cobrar(BuildContext context, int numero) {
    final mesa = sala.mesas.where((m) => m.numero == numero).firstOrNull;
    if (mesa == null) {
      avisar(context, 'No se encontró la mesa $numero.');
      return;
    }
    // La cuenta de siempre: detalle, documento si el local emite, y cobrar.
    abrirCuenta(context, sala, mesa);
  }

  @override
  Widget build(BuildContext context) {
    if (porCobrar.isEmpty) {
      return const _TextoVacio('Ninguna mesa espera la cuenta.');
    }
    final c = Colores.de(context);
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        for (final g in porCobrar)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Card(
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: BorderSide(color: c.aviso, width: 1.5),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            'Mesa ${g.numero}',
                            style: const TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 16,
                            ),
                          ),
                        ),
                        Text(
                          soles(g.total),
                          style: TextStyle(
                            fontWeight: FontWeight.w800,
                            color: c.dinero,
                            fontFeatures: cifras,
                          ),
                        ),
                      ],
                    ),
                    Text(
                      g.pedidos == 1
                          ? '1 pedido entregado'
                          : '${g.pedidos} pedidos entregados',
                      style: TextStyle(color: c.textoSuave, fontSize: 13),
                    ),
                    const SizedBox(height: 10),
                    FilledButton.icon(
                      onPressed: () => _cobrar(context, g.numero),
                      icon: const Icon(Icons.point_of_sale),
                      label: const Text('Cobrar'),
                    ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// Resumen fijo: cuánto hay en cocina, cuánto por cobrar y —solo para el
/// admin— el vendido del turno. Para otra cuenta ese dato sería un 403 en
/// cada vuelta del reloj.
class PieUnificado extends StatelessWidget {
  const PieUnificado({
    super.key,
    required this.sala,
    required this.porCobrar,
    required this.verVendido,
    required this.cajaGate,
  });

  final Sala sala;
  final List<PorCobrar> porCobrar;
  final bool verVendido;
  final CajaGate cajaGate;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final totalPorCobrar = porCobrar.fold<double>(0, (s, g) => s + g.total);
    final vendido = sala.vendido;
    Widget dato(String valor, String texto, [Color? color]) => Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: valor,
            style: TextStyle(
              fontWeight: FontWeight.w800,
              color: color,
              fontFeatures: cifras,
            ),
          ),
          TextSpan(text: ' $texto'),
        ],
      ),
    );
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: c.superficie,
        border: Border(top: BorderSide(color: c.borde)),
      ),
      child: Wrap(
        spacing: 18,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          // PEDIDOS y no mesas: todo pedido para llevar es la "mesa 0", y
          // contar mesas distintas los fundiría en uno solo.
          dato('${sala.cocina.length}', 'en cocina'),
          dato(soles(totalPorCobrar), 'por cobrar', c.aviso),
          if (verVendido && vendido != null)
            dato(soles(vendido), 'vendido', c.dinero),
          Text(hora(DateTime.now()), style: TextStyle(color: c.textoSuave)),
          ListenableBuilder(
            listenable: cajaGate,
            builder: (context, _) => cajaGate.abierta == false
                ? const Pastilla('Caja cerrada', tipo: TipoEstado.peligro)
                : const Pastilla('Caja abierta', tipo: TipoEstado.exito),
          ),
        ],
      ),
    );
  }
}
