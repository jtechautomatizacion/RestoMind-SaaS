import 'package:flutter/material.dart';

import 'app.dart';
import 'core/servicios.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(RestoMindApp(servicios: Servicios.produccion()));
}
