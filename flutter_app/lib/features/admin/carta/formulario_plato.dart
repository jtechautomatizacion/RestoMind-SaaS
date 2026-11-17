import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../../core/api/api_error.dart';
import '../../../core/plataforma/plataforma.dart';
import '../../../core/servicios.dart';
import '../../../design/tema.dart';
import '../../../design/widgets.dart';
import 'foto_plato.dart';
import 'modelos.dart';
import 'repo.dart';

/// Abre el formulario de un plato nuevo ([plato] null) o existente.
/// [alCambiarFoto] avisa qué plato cambió de foto, para que su miniatura no
/// siga mostrando la anterior.
Future<void> abrirFormularioPlato(
  BuildContext context, {
  required List<Categoria> categorias,
  Plato? plato,
  required void Function(int platoId) alCambiarFoto,
}) => mostrarHoja<void>(
  context,
  (_) => _FormularioPlato(
    categorias: categorias,
    plato: plato,
    alCambiarFoto: alCambiarFoto,
  ),
);

class _FormularioPlato extends StatefulWidget {
  const _FormularioPlato({
    required this.categorias,
    required this.plato,
    required this.alCambiarFoto,
  });

  final List<Categoria> categorias;
  final Plato? plato;
  final void Function(int platoId) alCambiarFoto;

  @override
  State<_FormularioPlato> createState() => _FormularioPlatoState();
}

class _FormularioPlatoState extends State<_FormularioPlato> {
  final _form = GlobalKey<FormState>();
  late final _nombre = TextEditingController(text: widget.plato?.nombre);
  late final _precio = TextEditingController(
    text: widget.plato?.precioVenta.toStringAsFixed(2),
  );
  late final _descripcion = TextEditingController(
    text: widget.plato?.descripcion,
  );
  late String? _categoria = widget.plato?.categoria;

  /// Foto elegida que todavía no se subió: se sube DESPUÉS de guardar el
  /// plato, porque un plato nuevo recién tiene id cuando el servidor lo crea.
  ArchivoElegido? _fotoNueva;
  Uint8List? _vistaPrevia;
  late String? _fotoGuardada = widget.plato?.imagenUrl;
  bool _ocupado = false;

  bool get _editando => widget.plato != null;

  /// Si el plato tiene una categoría que ya no está en el catálogo, se ofrece
  /// igual: así no se pierde el dato ni se bloquea el guardado.
  List<(String, IconData)> get _opciones => [
    for (final c in widget.categorias) (c.nombre, iconoDe(c.icono)),
    if (_categoria != null &&
        !widget.categorias.any((c) => c.nombre == _categoria))
      (_categoria!, Icons.restaurant),
  ];

  @override
  void dispose() {
    _nombre.dispose();
    _precio.dispose();
    _descripcion.dispose();
    super.dispose();
  }

  Future<void> _elegirFoto() async {
    final archivo = await Servicios.leer(context).plataforma.elegirImagen();
    if (archivo == null || !mounted) return;
    setState(() {
      _fotoNueva = archivo;
      _vistaPrevia = Uint8List.fromList(archivo.bytes);
    });
  }

  Future<void> _quitarFoto() async {
    if (_fotoNueva != null) {
      setState(() {
        _fotoNueva = null;
        _vistaPrevia = null;
      });
      return;
    }
    final plato = widget.plato;
    if (plato == null || _fotoGuardada == null) return;
    setState(() => _ocupado = true);
    try {
      await CartaRepo(Servicios.leer(context).api).quitarFoto(plato.id);
      if (!mounted) return;
      widget.alCambiarFoto(plato.id);
      setState(() => _fotoGuardada = null);
      avisar(context, 'Foto quitada', tipo: TipoAviso.exito);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _guardar() async {
    if (!_form.currentState!.validate()) return;
    final repo = CartaRepo(Servicios.leer(context).api);
    final descripcion = _descripcion.text.trim();
    final borrador = BorradorPlato(
      nombre: _nombre.text.trim(),
      categoria: _categoria!,
      precioVenta: leerPrecio(_precio.text)!,
      descripcion: descripcion.isEmpty ? null : descripcion,
    );
    setState(() => _ocupado = true);
    final Plato plato;
    try {
      plato = _editando
          ? await repo.editarPlato(widget.plato!.id, borrador)
          : await repo.crearPlato(borrador);
    } on ApiError catch (e) {
      if (mounted) {
        avisar(context, e);
        setState(() => _ocupado = false);
      }
      return;
    }
    // El plato ya quedó guardado: si la foto falla, la hoja se cierra igual.
    // Dejarla abierta invitaría a guardar de nuevo y duplicar un plato nuevo.
    var aviso = _editando ? 'Plato actualizado' : 'Plato creado';
    var tipo = TipoAviso.exito;
    final foto = _fotoNueva;
    if (foto != null) {
      try {
        await repo.subirFoto(plato.id, foto);
        widget.alCambiarFoto(plato.id);
      } on ApiError catch (e) {
        aviso = 'El plato se guardó, pero la foto no se subió: ${e.mensaje}';
        tipo = TipoAviso.error;
      }
    }
    if (!mounted) return;
    avisar(context, aviso, tipo: tipo);
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final opciones = _opciones;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Form(
        key: _form,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              _editando ? 'Editar plato' : 'Nuevo plato',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 16),
            _SelectorFoto(
              vistaPrevia: _vistaPrevia,
              guardada: _fotoGuardada,
              ocupado: _ocupado,
              elegir: _elegirFoto,
              quitar: _quitarFoto,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _nombre,
              maxLength: 100,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Nombre',
                hintText: 'Ej: Lomo saltado',
              ),
              validator: (v) =>
                  (v ?? '').trim().isEmpty ? 'Escriba el nombre' : null,
            ),
            const SizedBox(height: 8),
            if (opciones.isEmpty)
              Text(
                'Primero cree una categoría con el botón "Categorías".',
                style: TextStyle(color: c.peligro),
              )
            else
              DropdownButtonFormField<String>(
                initialValue: _categoria,
                decoration: const InputDecoration(labelText: 'Categoría'),
                items: [
                  for (final (nombre, icono) in opciones)
                    DropdownMenuItem(
                      value: nombre,
                      child: Row(
                        children: [
                          Icon(icono, size: 18, color: c.textoSuave),
                          const SizedBox(width: 8),
                          Text(nombre),
                        ],
                      ),
                    ),
                ],
                onChanged: (v) => setState(() => _categoria = v),
                validator: (v) => v == null ? 'Elija una categoría' : null,
              ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _precio,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Precio de venta',
                prefixText: 'S/ ',
                hintText: '45.00',
              ),
              validator: errorPrecio,
            ),
            const SizedBox(height: 16),
            TextFormField(
              controller: _descripcion,
              maxLength: 300,
              maxLines: 3,
              minLines: 2,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Descripción (opcional)',
                hintText: 'Ingredientes, tamaño, acompañamiento…',
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _ocupado || opciones.isEmpty ? null : _guardar,
              child: Text(_ocupado ? 'Guardando…' : 'Guardar'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Recuadro de la foto: muestra la elegida (aún sin subir) o la guardada, y
/// los botones para cambiarla o quitarla.
class _SelectorFoto extends StatelessWidget {
  const _SelectorFoto({
    required this.vistaPrevia,
    required this.guardada,
    required this.ocupado,
    required this.elegir,
    required this.quitar,
  });

  final Uint8List? vistaPrevia;
  final String? guardada;
  final bool ocupado;
  final VoidCallback elegir;
  final VoidCallback quitar;

  @override
  Widget build(BuildContext context) {
    final c = Colores.de(context);
    final previa = vistaPrevia;
    final tieneFoto = previa != null || guardada != null;
    final vista = previa != null
        ? ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: Image.memory(
              previa,
              width: 96,
              height: 96,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => const FotoPlato(url: null, lado: 96),
            ),
          )
        : FotoPlato(url: guardada, lado: 96);
    return Row(
      children: [
        vista,
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Foto del plato (opcional)',
                style: TextStyle(color: c.textoSuave, fontSize: 13),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: ocupado ? null : elegir,
                icon: const Icon(Icons.add_photo_alternate_outlined),
                label: Text(tieneFoto ? 'Cambiar foto' : 'Elegir foto'),
              ),
              if (tieneFoto)
                TextButton(
                  onPressed: ocupado ? null : quitar,
                  style: TextButton.styleFrom(foregroundColor: c.peligro),
                  child: const Text('Quitar foto'),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
