package pe.jtech.restomind

import android.webkit.JavascriptInterface

/**
 * Lo único que el lado nativo le presta a la app web: el token de FCM.
 *
 * El REGISTRO contra el backend lo hace el JavaScript, que es quien tiene el
 * JWT de la sesión. Duplicar la autenticación acá sería una segunda copia que
 * mantener sincronizada, y el día que cambie el login habría que acordarse de
 * tocar los dos lados.
 *
 * El nombre con el que se inyecta ("RestoMindNativo") tiene que coincidir con
 * el que busca frontend/js/push-notifications.js. Son dos archivos distintos
 * que deben decir lo mismo.
 */
class PuenteNativo {

    /** Devuelve "" mientras FCM todavía no generó el token — el JS lo
     *  reintenta en la siguiente vuelta, no es un error. */
    @JavascriptInterface
    fun obtenerTokenFCM(): String = TokenFCM.valor ?: ""
}

/**
 * Guarda el token que entrega Firebase.
 *
 * @Volatile porque lo escribe el hilo de FCM (onNewToken / addOnCompleteListener)
 * y lo lee el hilo del WebView cuando el JavaScript llama al puente. Sin eso,
 * el lector podría quedarse con una copia vieja en caché y devolver "" para
 * siempre aunque el token ya exista.
 */
object TokenFCM {
    @Volatile
    var valor: String? = null
}
