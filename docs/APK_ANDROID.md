# 📱 Empaquetar RestoMind como APK (WebView + FCM nativo)

Guía para armar el proyecto Android en Android Studio. Asume que la app web
ya está en producción sobre HTTPS (`https://app.jtechsolutiones.com`).

---

## Lo que NO funciona solo dentro de un WebView

`android.webkit.WebView` no es Chrome. Comparte el motor de renderizado,
pero le faltan APIs completas — y lo caro es que **casi todas fallan en
silencio**: sin excepción, sin log, sin nada en pantalla. La función
devuelve `null` y la app sigue como si todo estuviera bien.

| Qué | Qué pasa sin código nativo | Se resuelve en |
|---|---|---|
| **Notificaciones push** | La API no existe. El cocinero no recibe ninguna comanda | §3 y §4 |
| **Subir fotos de platos** | `<input type="file">` no abre nada al tocarlo | §5 |
| **Descargas** | Los enlaces de descarga no hacen nada | §5 |
| **Permiso de notificar** (Android 13+) | Se descartan todas sin preguntar | §6 |

Ninguna de las cuatro da error. Por eso van todas acá: son las que uno
descubre con la app ya instalada en el local.

---

## 1. Crear el proyecto

Android Studio → **New Project → Empty Views Activity**, lenguaje **Kotlin**,
`minSdk 24`.

## 2. Firebase

1. En la consola de Firebase: **Agregar app → Android**.
2. El *nombre del paquete* tiene que ser **exactamente** el `applicationId`
   de tu `build.gradle.kts` (p. ej. `pe.jtech.restomind`). Si no coincide,
   FCM no entrega nada y tampoco avisa por qué.
3. Descargá `google-services.json` y ponelo en la carpeta `app/`.

`build.gradle.kts` (raíz):
```kotlin
plugins {
    id("com.google.gms.google-services") version "4.4.2" apply false
}
```

`app/build.gradle.kts`:
```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.gms.google-services")
}

dependencies {
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging-ktx")
    implementation("androidx.core:core-ktx:1.15.0")
}
```

## 3. El puente con la app web

El lado nativo **solo entrega el token**. El registro contra el backend lo
hace el JavaScript, que es quien tiene el JWT de la sesión: duplicar la
autenticación en Kotlin sería una segunda copia que mantener sincronizada,
y el día que cambie el login habría que acordarse de tocar los dos lados.

`PuenteNativo.kt`:
```kotlin
package pe.jtech.restomind

import android.webkit.JavascriptInterface

class PuenteNativo {
    /** Lo llama frontend/js/push-notifications.js (_tokenNativo).
     *  Devuelve "" mientras FCM todavía no generó el token: el JS lo
     *  reintenta en la siguiente vuelta, no es un error. */
    @JavascriptInterface
    fun obtenerTokenFCM(): String = TokenFCM.valor ?: ""
}

object TokenFCM {
    @Volatile var valor: String? = null
}
```

> El nombre `RestoMindNativo` con el que se inyecta (§5) tiene que coincidir
> con el que busca `push-notifications.js`. Son dos archivos distintos que
> deben decir lo mismo.

## 4. Recibir las notificaciones

```kotlin
package pe.jtech.restomind

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

// DEBE ser idéntico a CANAL_ANDROID_COMANDAS en
// backend/utils/push_notifications.py. Si no coinciden, Android DESCARTA el
// mensaje sin mostrar nada: el servidor registra el envío como exitoso y en
// la cocina no suena nada.
const val CANAL_COMANDAS = "comandas"

class ServicioMensajes : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        // FCM rota el token (reinstalación, restauración de backup, limpieza
        // de datos). Guardarlo acá hace que el JS lo lea y lo re-registre en
        // la próxima activación.
        TokenFCM.valor = token
    }

    override fun onMessageReceived(mensaje: RemoteMessage) {
        // Con la app EN PRIMER PLANO, Android no dibuja nada solo: hay que
        // construir la notificación. En segundo plano sí la muestra el
        // sistema, usando channel_id — por eso el canal tiene que existir
        // aunque este método no se ejecute nunca.
        val n = mensaje.notification ?: return
        val aviso = NotificationCompat.Builder(this, CANAL_COMANDAS)
            .setSmallIcon(R.drawable.ic_notificacion)
            .setContentTitle(n.title ?: "Nueva comanda")
            .setContentText(n.body ?: "")
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .build()

        if (NotificationManagerCompat.from(this).areNotificationsEnabled()) {
            NotificationManagerCompat.from(this).notify(System.currentTimeMillis().toInt(), aviso)
        }
    }
}

fun crearCanalComandas(ctx: Context) {
    // Idempotente: crear un canal que ya existe no hace nada. Se llama en
    // cada arranque para cubrir el caso de una actualización de la app.
    val canal = NotificationChannel(
        CANAL_COMANDAS,
        "Comandas de cocina",
        NotificationManager.IMPORTANCE_HIGH,   // HIGH = suena y aparece encima
    ).apply {
        description = "Avisa cuando entra un pedido nuevo"
        enableVibration(true)
    }
    ctx.getSystemService(NotificationManager::class.java).createNotificationChannel(canal)
}
```

## 5. La Activity

```kotlin
package pe.jtech.restomind

import android.net.Uri
import android.os.Bundle
import android.webkit.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.google.firebase.messaging.FirebaseMessaging

class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private var archivoPendiente: ValueCallback<Array<Uri>>? = null

    private val elegirArchivo = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { resultado ->
        archivoPendiente?.onReceiveValue(
            WebChromeClient.FileChooserParams.parseResult(resultado.resultCode, resultado.data)
        )
        archivoPendiente = null
    }

    private val pedirPermisoNotificar = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* si lo niega, la app funciona igual: solo no vibra el aviso */ }

    override fun onCreate(estado: Bundle?) {
        super.onCreate(estado)

        crearCanalComandas(this)

        // Android 13+ exige permiso explícito para notificar. Sin pedirlo,
        // el sistema descarta TODAS las notificaciones sin preguntar nada.
        if (android.os.Build.VERSION.SDK_INT >= 33) {
            pedirPermisoNotificar.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }

        FirebaseMessaging.getInstance().token.addOnCompleteListener { t ->
            if (t.isSuccessful) TokenFCM.valor = t.result
        }

        web = WebView(this)
        setContentView(web)

        web.settings.apply {
            javaScriptEnabled = true
            // Sin esto, localStorage tira excepción y la app no puede ni
            // guardar la sesión: el login no persiste entre arranques.
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
        }

        web.addJavascriptInterface(PuenteNativo(), "RestoMindNativo")

        // Sin un WebViewClient propio, cualquier enlace abre el navegador
        // del sistema y el usuario "se sale" de la app.
        web.webViewClient = WebViewClient()

        // Habilita <input type="file">. Sin esto, el admin toca "subir foto"
        // del plato y no pasa absolutamente nada.
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                vista: WebView?,
                callback: ValueCallback<Array<Uri>>?,
                params: FileChooserParams?,
            ): Boolean {
                archivoPendiente?.onReceiveValue(null)
                archivoPendiente = callback
                elegirArchivo.launch(params?.createIntent())
                return true
            }
        }

        web.loadUrl("https://app.jtechsolutiones.com/static/index.html")
    }

    // El botón "atrás" tiene que navegar dentro de la app, no cerrarla.
    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }
}
```

## 6. `AndroidManifest.xml`

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />

<application
    android:icon="@mipmap/ic_launcher"
    android:label="RestoMind"
    android:usesCleartextTraffic="false">

    <activity android:name=".MainActivity" android:exported="true">
        <intent-filter>
            <action android:name="android.intent.action.MAIN" />
            <category android:name="android.intent.category.LAUNCHER" />
        </intent-filter>
    </activity>

    <service
        android:name=".ServicioMensajes"
        android:exported="false">
        <intent-filter>
            <action android:name="com.google.firebase.MESSAGING_EVENT" />
        </intent-filter>
    </service>
</application>
```

`usesCleartextTraffic="false"` a propósito: obliga a que todo salga por
HTTPS. Si algún día alguien apunta la app a `http://` para probar, que
falle ruidosamente en vez de mandar los JWT en texto plano por el wifi del
local.

---

## Probar que de verdad llega

No alcanza con que compile. El orden importa, porque cada paso depende del
anterior:

1. **Instalar y entrar** con una cuenta de rol `jefe_cocina` o `asistente`.
   Aceptá el permiso de notificaciones cuando lo pida.
2. **Confirmar que el token se registró.** En el VPS:
   ```bash
   sqlite3 /home/restomind/app/restomind.db \
     "SELECT usuario_id, substr(token,1,25) FROM push_subscriptions;"
   ```
   Si está vacío, el puente no entregó token: revisá que el nombre
   inyectado sea `RestoMindNativo` y que `google-services.json` tenga el
   `applicationId` correcto.
3. **Minimizar la app** (no cerrarla) y tomar un pedido desde otro
   dispositivo. Tiene que sonar.
4. **Cerrarla del todo** y repetir. Si llega minimizada pero no cerrada, el
   problema es el canal o la prioridad, no el token.
5. **Probar una foto de plato** desde Admin → Carta. Si al tocar no abre el
   selector, falta el `onShowFileChooser` de §5.

Si el envío figura exitoso en el servidor y en el celular no aparece nada,
el sospechoso número uno es el `channel_id`: tiene que decir `comandas` en
los dos lados.

```bash
journalctl -u restomind -f | grep -i push
```

---

## Lo que este camino cuesta, para tenerlo presente

Cada corrección del frontend exige **recompilar y redistribuir el APK**, y
esperar a que cada local lo instale. Con la alternativa TWA (el APK es una
cáscara sobre Chrome) los cambios subidos al VPS llegan solos, y el push
web funciona sin nada de este archivo.

Se eligió WebView por control del contenedor nativo. Queda anotado para el
día que la redistribución empiece a molestar: migrar a TWA no obliga a
tocar el backend, solo se reemplaza el proyecto Android.
