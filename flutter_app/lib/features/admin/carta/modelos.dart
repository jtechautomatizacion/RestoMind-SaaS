import 'package:flutter/material.dart';

import '../../../core/formato.dart';

/// Un plato de la carta (PlatoResponse del backend).
@immutable
class Plato {
  const Plato({
    required this.id,
    required this.nombre,
    required this.categoria,
    required this.precioVenta,
    this.descripcion,
    this.imagenUrl,
  });

  factory Plato.desdeJson(Map<String, dynamic> j) => Plato(
    id: j['id'] as int,
    nombre: j['nombre'] as String? ?? '',
    categoria: j['categoria'] as String? ?? '',
    precioVenta: aDouble(j['precio_venta']),
    descripcion: j['descripcion'] as String?,
    imagenUrl: j['imagen_url'] as String?,
  );

  final int id;
  final String nombre;
  final String categoria;
  final double precioVenta;
  final String? descripcion;

  /// Ruta relativa al mismo origen (`/static/assets/platos/7.jpg`).
  final String? imagenUrl;
}

/// Categoría del catálogo (CategoriaResponse). El backend guarda el ícono como
/// emoji; la app no trae fuente de emojis, así que se pinta con [iconoDe].
@immutable
class Categoria {
  const Categoria({
    required this.id,
    required this.nombre,
    required this.icono,
  });

  factory Categoria.desdeJson(Map<String, dynamic> j) => Categoria(
    id: j['id'] as int,
    nombre: j['nombre'] as String? ?? '',
    icono: j['icono'] as String? ?? iconoPorDefecto,
  );

  final int id;
  final String nombre;
  final String icono;
}

/// Lo que se carga de una vez para pintar la sección.
@immutable
class DatosCarta {
  const DatosCarta(this.platos, this.categorias);
  final List<Plato> platos;
  final List<Categoria> categorias;

  IconData iconoDeCategoria(String nombre) {
    for (final c in categorias) {
      if (c.nombre == nombre) return iconoDe(c.icono);
    }
    return Icons.restaurant;
  }
}

/// Lo que se manda al crear o editar un plato.
@immutable
class BorradorPlato {
  const BorradorPlato({
    required this.nombre,
    required this.categoria,
    required this.precioVenta,
    this.descripcion,
  });

  final String nombre;
  final String categoria;
  final double precioVenta;
  final String? descripcion;

  Map<String, Object?> aJson() => {
    'nombre': nombre,
    'categoria': categoria,
    'precio_venta': precioVenta,
    'descripcion': descripcion,
  };
}

/// Paleta fija de íconos de categoría: el valor es el emoji que ya guardan las
/// categorías creadas desde la app anterior, así las dos siguen entendiéndose.
const iconoPorDefecto = '🍽️';

const List<(String, IconData, String)> paletaIconos = [
  ('🍽️', Icons.restaurant, 'General'),
  ('🐟', Icons.set_meal, 'Pescados y mariscos'),
  ('🍤', Icons.tapas, 'Piqueos marinos'),
  ('🍣', Icons.bento, 'Sushi / Nikkei'),
  ('🍚', Icons.rice_bowl, 'Arroces'),
  ('🍜', Icons.ramen_dining, 'Fideos / Chifa'),
  ('🥟', Icons.dinner_dining, 'Chifa'),
  ('🥡', Icons.takeout_dining, 'Para llevar'),
  ('🍲', Icons.soup_kitchen, 'Sopas / Caldos'),
  ('🍗', Icons.kebab_dining, 'Pollo / Pollería'),
  ('🍟', Icons.fastfood, 'Frituras'),
  ('🥩', Icons.outdoor_grill, 'Carnes / Parrilla'),
  ('🍕', Icons.local_pizza, 'Pizza'),
  ('🍔', Icons.lunch_dining, 'Hamburguesas'),
  ('🥪', Icons.bakery_dining, 'Sándwiches'),
  ('🌮', Icons.brunch_dining, 'Antojitos'),
  ('🍳', Icons.egg, 'Desayunos'),
  ('🥗', Icons.eco, 'Ensaladas'),
  ('🥤', Icons.local_drink, 'Bebidas frías'),
  ('☕', Icons.local_cafe, 'Bebidas calientes'),
  ('🍷', Icons.wine_bar, 'Licores'),
  ('🍮', Icons.cookie, 'Postres'),
  ('🍰', Icons.cake, 'Pasteles'),
  ('🍦', Icons.icecream, 'Helados'),
];

IconData iconoDe(String emoji) {
  for (final (valor, icono, _) in paletaIconos) {
    if (valor == emoji) return icono;
  }
  return Icons.restaurant;
}

/// Categorías que tienen al menos un plato, en el orden de la carta. Se sacan
/// de los platos y no del catálogo: un plato cuya categoría ya se borró del
/// catálogo tiene que seguir teniendo un chip para encontrarlo.
List<String> categoriasEnUso(List<Plato> platos) => [
  ...{for (final p in platos) p.categoria},
];

List<Plato> filtrarPorCategoria(List<Plato> platos, String? categoria) =>
    categoria == null
    ? platos
    : platos.where((p) => p.categoria == categoria).toList();

/// Precio tal como lo tipea el cajero: acepta coma o punto, hasta dos
/// decimales y mayor a cero (lo mismo que exige el backend con `gt=0`).
double? leerPrecio(String texto) {
  final t = texto.trim().replaceAll(',', '.');
  if (!RegExp(r'^\d+(\.\d{1,2})?$').hasMatch(t)) return null;
  final v = double.parse(t);
  return v > 0 ? v : null;
}

String? errorPrecio(String? texto) {
  final t = (texto ?? '').trim();
  if (t.isEmpty) return 'Escriba el precio';
  if (leerPrecio(t) == null) {
    return 'Escriba un precio mayor a 0, con hasta dos decimales';
  }
  return null;
}
