import 'package:flutter/material.dart';

import '../../core/api/api_error.dart';
import '../../core/config.dart';
import '../../core/formato.dart';
import '../../design/tema.dart';
import '../../design/widgets.dart';
import 'metodo_pago.dart';
import 'modelos.dart';
import 'repo.dart';

/// Nuevo pedido de una mesa o PARA LLEVAR ([mesa] null). Es la misma hoja,
/// misma carta y mismo carrito: duplicarla sería tener dos versiones de lo
/// mismo que se desincronizan. Devuelve la comanda creada.
class HojaPedido extends StatefulWidget {
  const HojaPedido({
    super.key,
    required this.repo,
    required this.carta,
    this.mesa,
  });

  final MesasRepo repo;

  /// La carta que ya se tenía; si está vacía se pide al abrir.
  final List<Plato> carta;
  final Mesa? mesa;

  @override
  State<HojaPedido> createState() => _HojaPedidoState();
}

class _HojaPedidoState extends State<HojaPedido> {
  late Future<List<Plato>> _carta = _cargar();
  String? _categoria;

  /// plato_id → cantidad, en el orden en que se agregaron.
  final Map<int, int> _carrito = {};
  final Map<int, Plato> _platos = {};

  /// Siempre arranca en efectivo: conservar lo último elegido haría que un
  /// Yape suelto se arrastre a los pedidos siguientes, y eso recién se nota
  /// al cerrar la caja.
  MetodoPago _metodo = MetodoPago.efectivo;
  bool _enviando = false;

  bool get _paraLlevar => widget.mesa == null;

  Future<List<Plato>> _cargar() async {
    final todos = widget.carta.isNotEmpty
        ? widget.carta
        : await widget.repo.carta();
    final activos = todos.where((p) => p.activo).toList();
    for (final p in activos) {
      _platos[p.id] = p;
    }
    return activos;
  }

  double get _total => _carrito.entries.fold<double>(
    0,
    (s, e) => s + _platos[e.key]!.precio * e.value,
  );

  void _agregar(Plato p) =>
      setState(() => _carrito.update(p.id, (n) => n + 1, ifAbsent: () => 1));

  void _quitar(int platoId) => setState(() {
    final n = _carrito[platoId]!;
    if (n > 1) {
      _carrito[platoId] = n - 1;
    } else {
      _carrito.remove(platoId);
    }
  });

  Future<void> _enviar() async {
    if (_carrito.isEmpty) {
      avisar(context, 'Agregue al menos un plato.');
      return;
    }
    // Para llevar se cobra en este mismo acto: es mover plata.
    if (_paraLlevar &&
        !await confirmar(
          context,
          titulo: 'Cobrar para llevar',
          mensaje:
              'Se cobran ${soles(_total)} en ${_metodo.etiqueta} y el pedido '
              'pasa a cocina.',
          accion: 'Cobrar',
        )) {
      return;
    }
    setState(() => _enviando = true);
    try {
      final comanda = await widget.repo.crearComanda(
        numeroMesa: widget.mesa?.numero ?? 0,
        paraLlevar: _paraLlevar,
        cantidades: Map.of(_carrito),
        metodo: _metodo,
      );
      if (mounted) Navigator.pop(context, (comanda, _metodo));
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) => SizedBox(
    height: MediaQuery.sizeOf(context).height * .88,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 8, 8),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _paraLlevar
                      ? 'Para llevar · Nuevo pedido'
                      : 'Mesa ${widget.mesa!.numero} · Nuevo pedido',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Cerrar',
                onPressed: () => Navigator.pop(context),
                icon: const Icon(Icons.close),
              ),
            ],
          ),
        ),
        Expanded(
          child: FutureBuilder<List<Plato>>(
            future: _carta,
            builder: (context, s) {
              if (s.hasError) {
                return ErrorCarga(
                  error: s.error!,
                  reintentar: () => setState(() => _carta = _cargar()),
                );
              }
              if (!s.hasData) {
                return const Center(child: CircularProgressIndicator());
              }
              return _Carta(
                platos: s.data!,
                categoria: _categoria,
                alElegirCategoria: (c) => setState(() => _categoria = c),
                alAgregar: _agregar,
              );
            },
          ),
        ),
        _Pie(
          lineas: [
            for (final e in _carrito.entries) (_platos[e.key]!, e.value),
          ],
          total: _total,
          paraLlevar: _paraLlevar,
          metodo: _metodo,
          enviando: _enviando,
          alCambiarMetodo: (m) => setState(() => _metodo = m),
          alQuitar: _quitar,
          alEnviar: _enviar,
        ),
      ],
    ),
  );
}

class _Carta extends StatelessWidget {
  const _Carta({
    required this.platos,
    required this.categoria,
    required this.alElegirCategoria,
    required this.alAgregar,
  });

  final List<Plato> platos;
  final String? categoria;
  final ValueChanged<String> alElegirCategoria;
  final ValueChanged<Plato> alAgregar;

  @override
  Widget build(BuildContext context) {
    if (platos.isEmpty) {
      return const Vacio(
        icono: Icons.restaurant_menu,
        titulo: 'La carta está vacía',
        mensaje: 'El administrador carga los platos en Admin > Carta.',
      );
    }
    final categorias = {for (final p in platos) p.categoria}.toList();
    final actual = categorias.contains(categoria)
        ? categoria!
        : categorias.first;
    final visibles = platos.where((p) => p.categoria == actual).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 48,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16),
            children: [
              for (final cat in categorias)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(cat),
                    selected: cat == actual,
                    onSelected: (_) => alElegirCategoria(cat),
                  ),
                ),
            ],
          ),
        ),
        Expanded(
          child: GridView.builder(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 360,
              mainAxisExtent: 84,
              crossAxisSpacing: 8,
              mainAxisSpacing: 8,
            ),
            itemCount: visibles.length,
            itemBuilder: (_, i) => _TarjetaPlato(
              plato: visibles[i],
              alTocar: () => alAgregar(visibles[i]),
            ),
          ),
        ),
      ],
    );
  }
}

class _TarjetaPlato extends StatelessWidget {
  const _TarjetaPlato({required this.plato, required this.alTocar});

  final Plato plato;
  final VoidCallback alTocar;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final sinFoto = Container(
      color: c.superficieAlt,
      alignment: Alignment.center,
      child: Icon(Icons.image_outlined, color: c.textoSuave),
    );
    final url = plato.imagenUrl;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: alTocar,
        child: Row(
          children: [
            SizedBox(
              width: 84,
              height: 84,
              child: url == null || url.isEmpty
                  ? sinFoto
                  : Image.network(
                      '$origenApi$url',
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => sinFoto,
                    ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 8,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      plato.nombre,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    if (plato.descripcion != null &&
                        plato.descripcion!.isNotEmpty)
                      Text(
                        plato.descripcion!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 12, color: c.textoSuave),
                      ),
                    const SizedBox(height: 2),
                    Text(
                      soles(plato.precio),
                      style: TextStyle(
                        fontWeight: FontWeight.w800,
                        color: c.dinero,
                        fontFeatures: cifras,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(right: 10),
              child: Icon(
                Icons.add_circle,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Pie extends StatelessWidget {
  const _Pie({
    required this.lineas,
    required this.total,
    required this.paraLlevar,
    required this.metodo,
    required this.enviando,
    required this.alCambiarMetodo,
    required this.alQuitar,
    required this.alEnviar,
  });

  final List<(Plato, int)> lineas;
  final double total;
  final bool paraLlevar;
  final MetodoPago metodo;
  final bool enviando;
  final ValueChanged<MetodoPago> alCambiarMetodo;
  final ValueChanged<int> alQuitar;
  final VoidCallback alEnviar;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    return Container(
      decoration: BoxDecoration(
        color: c.superficie,
        border: Border(top: BorderSide(color: c.borde)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (lineas.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                'Toque un plato para agregarlo',
                textAlign: TextAlign.center,
                style: TextStyle(color: c.textoSuave),
              ),
            )
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 150),
              child: ListView(
                shrinkWrap: true,
                children: [
                  for (final (plato, cantidad) in lineas)
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '$cantidad x ${plato.nombre}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        Text(
                          soles(plato.precio * cantidad),
                          style: const TextStyle(fontFeatures: cifras),
                        ),
                        IconButton(
                          tooltip: 'Quitar uno',
                          visualDensity: VisualDensity.compact,
                          onPressed: () => alQuitar(plato.id),
                          icon: const Icon(Icons.remove_circle_outline),
                        ),
                      ],
                    ),
                ],
              ),
            ),
          FilaMonto('Total', soles(total), fuerte: true, color: c.dinero),
          if (paraLlevar) ...[
            SelectorMetodoPago(valor: metodo, alCambiar: alCambiarMetodo),
            const SizedBox(height: 10),
          ],
          FilledButton.icon(
            onPressed: enviando ? null : alEnviar,
            icon: Icon(paraLlevar ? Icons.point_of_sale : Icons.send),
            // Para llevar el botón cobra, no solo manda a cocina: decirlo
            // evita que se mande creyendo que todavía falta cobrar.
            label: Text(
              paraLlevar ? 'Cobrar y enviar a cocina' : 'Enviar a cocina',
            ),
          ),
        ],
      ),
    );
  }
}
