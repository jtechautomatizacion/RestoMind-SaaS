package pe.jtech.restomind

import android.annotation.SuppressLint
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

private const val URL_APP = "https://app.jtechsolutiones.com/static/index.html"

class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView
    private var archivoPendiente: ValueCallback<Array<Uri>>? = null

    private val elegirArchivo = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { resultado ->
        // SIEMPRE hay que contestarle al callback, incluso si el usuario
        // canceló. Si se lo deja sin respuesta, el <input type="file"> queda
        // bloqueado para siempre: los toques siguientes no abren nada y no
        // hay ningún error que lo explique.
        archivoPendiente?.onReceiveValue(
            WebChromeClient.FileChooserParams.parseResult(resultado.resultCode, resultado.data)
        )
        archivoPendiente = null
    }

    private val pedirPermisoNotificar = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* si lo niega, la app funciona igual: solo no avisa */ }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(estado: Bundle?) {
        super.onCreate(estado)

        // Android 13+ exige permiso explícito para notificar. Sin pedirlo, el
        // sistema descarta TODAS las notificaciones sin preguntar nada.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            pedirPermisoNotificar.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }

        web = WebView(this)
        setContentView(web)

        web.settings.apply {
            javaScriptEnabled = true
            // Sin domStorage, localStorage lanza excepción: la sesión no
            // persiste y el usuario tiene que loguearse en cada arranque.
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
        }

        web.addJavascriptInterface(PuenteNativo(), "RestoMindNativo")

        // Sin un WebViewClient propio, cualquier enlace abre el navegador del
        // sistema y el usuario "se sale" de la app.
        web.webViewClient = WebViewClient()

        // Habilita <input type="file">. Sin esto, el admin toca "subir foto"
        // del plato y no pasa absolutamente nada: ni selector, ni error.
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                vista: WebView?,
                callback: ValueCallback<Array<Uri>>?,
                params: FileChooserParams?,
            ): Boolean {
                archivoPendiente?.onReceiveValue(null)
                archivoPendiente = null

                val intent = params?.createIntent()
                if (intent == null) {
                    // Sin intent no hay selector que abrir. Se contesta que
                    // NO se maneja para que el WebView cierre el pedido por
                    // su cuenta; devolver true sin lanzar nada dejaría el
                    // <input type="file"> trabado para siempre.
                    callback?.onReceiveValue(null)
                    return false
                }

                return try {
                    elegirArchivo.launch(intent)
                    archivoPendiente = callback
                    true
                } catch (e: Exception) {
                    callback?.onReceiveValue(null)
                    false
                }
            }
        }

        // El botón "atrás" navega dentro de la app en vez de cerrarla de
        // golpe — cerrar con un pedido a medio cargar sería perderlo.
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) {
                    web.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        if (estado == null) web.loadUrl(URL_APP)
    }

    /** Conserva el historial del WebView al rotar la pantalla; sin esto,
     *  girar el celular recarga la app y se pierde lo que estaba en curso. */
    override fun onSaveInstanceState(estado: Bundle) {
        super.onSaveInstanceState(estado)
        web.saveState(estado)
    }

    override fun onRestoreInstanceState(estado: Bundle) {
        super.onRestoreInstanceState(estado)
        web.restoreState(estado)
    }
}
