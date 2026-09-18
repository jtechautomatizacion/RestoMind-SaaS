/**
 * A QUÉ BACKEND LE HABLA LA APP EMPAQUETADA.
 *
 * Este archivo existe para que el destino NO esté quemado dentro del código.
 * Antes vivía como una constante en capacitor-init.js, y la consecuencia fue
 * concreta: el APK "de pruebas" apuntaba a producción, así que cada prueba de
 * impresión creaba comandas reales en la base del restaurante. No había forma
 * de darse cuenta mirando la app.
 *
 * El valor que está acá es el de PRODUCCIÓN, y es el que se versiona.
 * `tools/preparar-apk.mjs` lo sobrescribe en la copia de `dist-apk/` cuando se
 * compila para pruebas — nunca en `frontend/`, para que el árbol de trabajo no
 * quede apuntando a la PC de alguien y eso termine en un commit.
 *
 *     npm run apk           -> producción (este valor)
 *     npm run apk:testing   -> el backend local de la PC
 *
 * TIENE QUE CARGAR ANTES QUE capacitor-init.js, que es quien lo lee.
 *
 * En el navegador no se usa: ahí la ruta relativa /api ya cae en el mismo
 * dominio que sirve la página.
 */
window.RESTOMIND_API_DESTINO = 'https://app.jtechsolutiones.com';

// --- Y ACÁ SE DECIDE CONTRA QUÉ ORIGEN HABLA LA PÁGINA ----------------------
//
// La decisión vive en ESTE archivo, y no en cada página, porque el proyecto
// tiene dos páginas (index.html y superadmin.html) y superadmin.js la tenía
// escrita aparte: `const API_BASE_URL = '/api'`, una ruta relativa.
//
// En el navegador eso funciona —la página y la API salen del mismo dominio—
// pero dentro del APK el origen es https://localhost, así que "/api/..." le
// pega al propio teléfono, que responde con index.html. El error que se ve es
//     Unexpected token '<' ... is not valid JSON
// porque el código esperaba JSON y recibió una página HTML. No dice nada
// sobre el origen, que es el problema real.
//
// Con la decisión en un solo lugar, una página nueva que cargue este archivo
// queda bien por defecto, sin tener que acordarse de nada.
window.RESTOMIND_ES_NATIVO = Boolean(
    window.Capacitor && typeof window.Capacitor.isNativePlatform === 'function'
        ? window.Capacitor.isNativePlatform()
        : false
);

// En la web queda vacío: la ruta relativa ya cae en el mismo dominio que
// sirve la página, y así el mismo frontend sirve para desarrollo, para el VPS
// y para el APK sin condicionales repartidos por el código.
window.RESTOMIND_API_BASE = window.RESTOMIND_ES_NATIVO
    ? (window.RESTOMIND_API_DESTINO || '')
    : '';

/**
 * La URL de un archivo servido por el backend (la foto de un plato, por
 * ejemplo), a partir de la ruta que guarda la base de datos.
 *
 * El backend guarda rutas RELATIVAS ("/static/assets/platos/5.jpg"), que en la
 * web resuelven solas. En el APK no: el origen es https://localhost y esa ruta
 * apunta al teléfono, donde esas fotos no están —ni pueden estar, porque son
 * de un restaurante y el APK es el mismo para todos—. Sin esto, las imágenes
 * simplemente no aparecen y nada explica por qué.
 */
window.urlDeArchivo = function (ruta) {
    if (!ruta) return ruta;
    // Ya es absoluta (http://, https://, data:, blob:): se deja como está.
    if (/^[a-z][a-z0-9+.-]*:/i.test(ruta)) return ruta;
    return (window.RESTOMIND_API_BASE || '') + ruta;
};
