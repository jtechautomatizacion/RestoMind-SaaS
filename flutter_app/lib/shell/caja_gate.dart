import 'dart:async';

import 'package:flutter/foundation.dart';

import '../core/api/api_client.dart';
import '../core/api/api_error.dart';

/// ¿Hay caja abierta? Mesas y Cocina se bloquean sin ella: sin saldo inicial no
/// hay contra qué reconciliar lo que entra.
///
/// GET /caja/gate no exige admin (mozo y cocina tienen que poder preguntar) y
/// nunca devuelve montos. Se consulta al entrar y cada 20 s, para que un mozo
/// con la app abierta se desbloquee solo cuando el dueño abre la caja desde
/// otro aparato.
class CajaGate extends ChangeNotifier {
  CajaGate(this._api);

  final ApiClient _api;
  Timer? _reloj;

  /// null = todavía no se sabe (no se bloquea nada mientras tanto).
  bool? abierta;

  void iniciar() {
    unawaited(refrescar());
    _reloj ??= Timer.periodic(const Duration(seconds: 20), (_) => refrescar());
  }

  Future<void> refrescar() async {
    try {
      final j = await _api.get('/caja/gate') as Map<String, dynamic>;
      final valor = j['hay_caja_abierta'] == true;
      if (valor != abierta) {
        abierta = valor;
        notifyListeners();
      }
    } on ApiError {
      // Sin red se conserva el último valor conocido: bloquear la sala por un
      // corte de wifi sería peor que dejarla operar.
    }
  }

  @override
  void dispose() {
    _reloj?.cancel();
    super.dispose();
  }
}
