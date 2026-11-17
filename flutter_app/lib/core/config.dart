/// Origen de la API. Vacío = el MISMO origen desde el que se sirve la app
/// (FastAPI o el nginx de delante sirven la app y publican /api). Es lo que
/// exige la cookie de sesión SameSite=Strict.
///
/// Solo para desarrollo contra otro origen: `--dart-define=API_BASE_URL=...`.
const String origenApi = String.fromEnvironment('API_BASE_URL');

/// Versión de la app web, la de pubspec.yaml (`--dart-define=APP_VERSION=...`
/// la pone tools/flutter-web.mjs al compilar).
const String versionApp = String.fromEnvironment(
  'APP_VERSION',
  defaultValue: 'dev',
);
