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
