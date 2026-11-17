import '../../core/api/api_client.dart';
import 'modelos.dart';

class DineroRepo {
  const DineroRepo(this._api);

  final ApiClient _api;

  Future<Resumen> resumen(Periodo periodo) async => Resumen.desdeJson(
    await _api.get('/dashboard/resumen', query: periodo.query)
        as Map<String, dynamic>,
  );

  /// El Excel lleva el MISMO período que se está viendo en pantalla.
  Future<Descarga> reporteExcel(Periodo periodo) => _api.descargar(
    '/dashboard/reporte-excel',
    query: periodo.query,
    nombrePorDefecto: 'reporte.xlsx',
  );
}
