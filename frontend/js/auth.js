/**
 * Login y sesión.
 *
 * Multi-tenant real: el token que devuelve /auth/login lleva el cliente_id
 * del restaurante — ya no se manda por header a mano (X-Cliente-Id), lo
 * resuelve el backend a partir de quién inició sesión. Sin esto, cualquiera
 * podía pedir los datos de otro restaurante con solo cambiar un header.
 */

const TOKEN_KEY = 'restomind_token';
const USUARIO_KEY = 'restomind_usuario';

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function getUsuarioGuardado() {
    try {
        return JSON.parse(localStorage.getItem(USUARIO_KEY) || 'null');
    } catch (_) {
        return null;
    }
}

function guardarSesion(accessToken, usuario) {
    localStorage.setItem(TOKEN_KEY, accessToken);
    localStorage.setItem(USUARIO_KEY, JSON.stringify(usuario));
}

function limpiarSesion() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USUARIO_KEY);
}

/**
 * Reset total (sesión + Service Worker + Cache Storage). La limpieza real
 * vive inline en index.html bajo el flag ?reset — acá solo se navega hasta
 * ahí. Es a propósito: esa versión corre antes que cualquier .js, así que
 * funciona incluso cuando el problema ES el JS cacheado, y tener una sola
 * implementación evita que se desincronicen (ya pasó una vez).
 */
function limpiarYRecargar() {
    window.location.href = '/static/index.html?reset';
}

function mostrarLogin(mensaje) {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');
}

function cambiarTabLogin(tab) {
    // Actualizar pestañas activas
    document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[onclick="cambiarTabLogin('${tab}')"]`).classList.add('active');

    // Actualizar formularios. El toggle real de visibilidad es la clase
    // "hidden" (usa !important, así que gana sobre ".login-form.active" si
    // ambas quedan puestas) — "active" solo queda como hook para estilos.
    document.getElementById('form-login-admin').classList.remove('active');
    document.getElementById('form-login-admin').classList.add('hidden');
    document.getElementById('form-login-staff').classList.remove('active');
    document.getElementById('form-login-staff').classList.add('hidden');

    const formActivo = document.getElementById(`form-login-${tab}`);
    formActivo.classList.add('active');
    formActivo.classList.remove('hidden');

    // Limpiar errores
    document.getElementById('login-error-admin').classList.add('hidden');
    document.getElementById('login-error-staff').classList.add('hidden');
}

function mostrarApp() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
}

async function loginAdmin(event) {
    event.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const boton = event.target.querySelector('button[type="submit"]');
    const errorEl = document.getElementById('login-error-admin');

    boton.disabled = true;
    boton.textContent = 'Ingresando...';
    errorEl.classList.add('hidden');

    try {
        const resp = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });

        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || 'No se pudo iniciar sesión');
        }

        const data = await resp.json();
        guardarSesion(data.access_token, data.usuario);
        aplicarUsuarioDeSesion(data.usuario);

        // Redirigir a superadmin a su panel si es superadmin
        if (data.usuario.rol === 'superadmin') {
            window.location.href = '/static/superadmin.html';
            return;
        }

        mostrarApp();
        init();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove('hidden');
    } finally {
        boton.disabled = false;
        boton.textContent = 'Ingresar';
    }
}

async function loginStaff(event) {
    event.preventDefault();
    const celular = document.getElementById('login-celular').value.trim();
    const password = document.getElementById('login-password-staff').value;
    const boton = event.target.querySelector('button[type="submit"]');
    const errorEl = document.getElementById('login-error-staff');

    boton.disabled = true;
    boton.textContent = 'Ingresando...';
    errorEl.classList.add('hidden');

    try {
        const resp = await fetch(`${API_BASE_URL}/auth/login-staff`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ celular, password }),
        });

        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || 'No se pudo iniciar sesión');
        }

        const data = await resp.json();
        guardarSesion(data.access_token, data.usuario);
        aplicarUsuarioDeSesion(data.usuario);
        mostrarApp();
        init();
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove('hidden');
    } finally {
        boton.disabled = false;
        boton.textContent = 'Ingresar';
    }
}

async function manejarLogin(event) {
    // Función legacy para compatibilidad (ahora se llamará loginAdmin o loginStaff según la pestaña)
    return loginAdmin(event);
}

function aplicarUsuarioDeSesion(usuario) {
    estado.clienteId = usuario.cliente_id;
    estado.usuario = usuario;

    // Los roles de una cuenta real mandan sobre el selector manual del
    // dispositivo (el botón redondo del header): si Pedro se loguea como
    // mozo, el celular pasa a comportarse como el de un mozo automáticamente,
    // sin que nadie tenga que tocar el selector. Este último queda como
    // respaldo para el caso "seguimos con un celular compartido sin cuentas
    // individuales", no como la fuente de verdad cuando sí hay login real.
    // usuario.roles es siempre un array (puede tener más de un rol — ver
    // backend/utils/roles.py) incluso cuando venía de un login viejo.
    localStorage.setItem('restomind_roles', JSON.stringify(usuario.roles));
    estado.roles = usuario.roles;

    const nombreCliente = document.getElementById('nombre-cliente-header');
    if (nombreCliente) nombreCliente.textContent = usuario.cliente_nombre;
}

function cerrarSesion() {
    limpiarSesion();
    // Recarga en limpio: más simple y confiable que intentar desmontar a
    // mano el estado de todas las pestañas (mesas cargadas, carritos
    // abiertos, etc.) para dejarlo como recién arrancado.
    window.location.reload();
}

// Se llama en vez de init() directamente al cargar la página: valida la
// sesión guardada contra el servidor (¿el token no expiró? ¿el usuario
// sigue activo?) antes de mostrar la app o el login.
async function initAuth() {
    const token = getToken();
    const usuarioGuardado = getUsuarioGuardado();
    if (!token || !usuarioGuardado) {
        mostrarLogin();
        return;
    }

    try {
        const resp = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` },
        });
        if (!resp.ok) throw new Error('Sesión expirada');

        const usuario = await resp.json();
        guardarSesion(token, usuario);
        aplicarUsuarioDeSesion(usuario);
        mostrarApp();
        init();
    } catch (_) {
        limpiarSesion();
        mostrarLogin('Tu sesión expiró. Ingresa de nuevo.');
    }
}

// Cualquier 401 (token vencido a media sesión, revocado, etc.) manda de
// vuelta al login en vez de dejar la app mostrando errores confusos.
function manejarSesionExpirada() {
    limpiarSesion();
    mostrarLogin('Tu sesión expiró. Ingresa de nuevo.');
}
