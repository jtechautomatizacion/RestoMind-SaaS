# RestoMind · app web (Flutter)

La interfaz de RestoMind para el navegador y como PWA instalable. Reemplaza al
frontend HTML/JS de `frontend/` en la web. Ese frontend **sigue existiendo solo
como fuente del APK de Android (Capacitor)** hasta que el APK también pase a
Flutter con la impresora Bluetooth.

## Comandos

Desde la raíz del repo:

```bash
npm run web          # compila esta app y la publica en ../web (lo que sirve FastAPI en /)
npm run verificar    # formato, analyze, pruebas de Flutter, pytest y la compilación al día
npm run local        # levanta todo en local (ver ../docs/LOCAL.md)
```

Desde `flutter_app/` (SDK en `C:\src\flutter\bin`, Flutter 3.47.7):

```bash
flutter pub get
dart format lib test
flutter analyze
flutter test
```

## Cómo está armada

```
lib/
  main.dart, app.dart        arranque, tema, login ↔ shell según la sesión
  core/
    api/api_client.dart      el ÚNICO cliente HTTP (ver "Sesión")
    api/api_error.dart       errores de la API ya traducidos para mostrar
    sesion.dart              Usuario + Sesion (ChangeNotifier)
    roles.dart               espejo de backend/utils/roles.py
    formato.dart             soles(), fechaLocal(), fechaHora(), html()...
    plataforma/              lo que depende del navegador (descargar, imprimir,
                             elegir una imagen, preferencias del aparato)
    servicios.dart           Servicios.de(context) → api, sesion, plataforma
  design/
    tema.dart                paleta (Colores.de(context)) y ThemeData
    widgets.dart             piezas comunes: avisar, confirmar, Pastilla,
                             Encabezado, Cargador, Vacio, Indicador, FilaMonto,
                             mostrarHoja...
  shell/
    shell.dart               barra superior, pestañas por rol, ShellScope
    caja_gate.dart           bloquea Mesas y Cocina sin caja abierta
  features/<pantalla>/       una carpeta por pantalla, con su propio
                             modelos.dart y repo.dart si los necesita
```

## Reglas

1. **Toda llamada pasa por `Servicios.de(context).api`.** Rutas sin el prefijo
   `/api` (`api.get('/mesas')`). Nunca `http` directo, nunca `fetch`.
2. **Errores:** la API lanza `ApiError`; se muestra con `avisar(context, e)`.
   Los errores de negocio con código estable se distinguen por `e.codigo`
   (`IDENTIFICAR_COMPRADOR`, `FACTURACION_DESACTIVADA`), nunca buscando
   palabras en el mensaje.
3. **Nada sensible en el navegador.** El token vive solo en memoria. En
   `plataforma.guardarPreferencia` van preferencias del aparato (tema, vista),
   nunca datos de la sesión ni del negocio.
4. **Los permisos los decide el backend.** `core/roles.dart` solo evita mostrar
   lo que el rol no puede usar; si la API responde 403, manda la API.
5. **Colores desde `Colores.de(context)`** (o `Theme.of(context).colorScheme`),
   nunca un `Color(0x...)` suelto en una pantalla: tiene que verse bien en los
   dos temas. Ámbar = esperando la cuenta, verde = éxito, rojo = peligro,
   teal (`dinero`) = plata.
6. **Dinero con `soles()`**, siempre dos decimales, sin redondear "para que se
   vea mejor". Fechas del backend con `fechaLocal()` (vienen en UTC sin zona).
7. **Nada de emojis en la interfaz**: la app empaqueta sus fuentes (sin CDN,
   por la CSP) y no trae fuente de emojis. Usar `Icons.*`.
8. **Acciones que mueven dinero o no se deshacen** (cobrar, cerrar caja,
   eliminar) piden confirmación con `confirmar()`. Ningún atajo de teclado
   cobra.
9. Comentarios: el PORQUÉ, no el qué. En español.

## Diseño: "lo que se imprime, se ve como impreso"

`design/papel.dart` es la identidad visual de la app, y tiene reglas estrictas
para que siga significando algo:

- **El papel térmico** (`TiraDePapel`: claro, borde troquelado, tinta oscura)
  se usa SOLO para lo que en el local sale impreso: la comanda en Cocina y en
  "Atiendo solo", y la pre-cuenta en la cuenta de una mesa. Si se usa en
  cualquier otra tarjeta, deja de distinguirse.
- **La letra impresa** (`impreso()`, IBM Plex Mono) va en lo que imprime la
  térmica: número de mesa, platos de la comanda, montos de la cuenta, hora y
  cronómetro. Las etiquetas y textos de la interfaz van en Inter.
- **Cocina es un riel**: el pedido más antiguo a la izquierda (arriba en el
  celular), y la barra del cronómetro se llena hasta los 15 minutos y pasa a
  rojo. Es lo que se lee de lejos.
- **En Mesas el estado es una franja de color** en el pie de la tarjeta, para
  leer la grilla por color.
- **Escala de texto fija** (12 / 14 / 16 / 20 / 28 / 40, en `temaRestoMind`) y
  títulos de sección en minúsculas normales (`TituloSeccion`), nunca en
  MAYÚSCULAS espaciadas.
- Sobre el papel, los colores con significado van en su versión oscura
  (`Papel.de(context).peligro`, `.aviso`, `.exito`), no los de `Colores`.

## Sesión (mismas reglas de seguridad que Sac-Geo)

- El login manda `X-Sesion: cookie`. El servidor responde un access token de
  15 minutos, que la app guarda SOLO en memoria, y pone la cookie HttpOnly
  `__Secure-restomind_refresh` (Secure, SameSite=Strict, Path=/api/auth/sesion).
- Al recargar la página, `Sesion.iniciar()` renueva con esa cookie: no se pide la
  contraseña de nuevo hasta que la sesión caduca (14 días) o se cierra.
- Un 401 dispara UNA renovación serializada. Presentar una cookie ya rotada se
  toma como robo: el servidor revoca la sesión entera.
- La app y la API tienen que servirse del MISMO origen (lo exige SameSite=Strict).
  En producción y en local, FastAPI (o el nginx de delante) sirve `../web` en `/`.
- La compilación va **sin CDN** (`--no-web-resources-cdn`, fuentes empaquetadas)
  y con `--csp`: la página no se conecta a ningún origen que no sea el propio.
