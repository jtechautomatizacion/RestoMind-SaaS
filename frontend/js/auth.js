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

function mostrarLogin(mensaje) {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');
    const error = document.getElementById('login-error');
    if (mensaje) {
        error.textContent = mensaje;
        error.classList.remove('hidden');
    } else {
        error.classList.add('hidden');
    }
}

function mostrarApp() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
}

async function manejarLogin(event) {
    event.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const boton = document.getElementById('btn-login');

    boton.disabled = true;
    boton.textContent = 'Ingresando...';

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
        mostrarApp();
        init();
    } catch (err) {
        mostrarLogin(err.message);
    } finally {
        boton.disabled = false;
        boton.textContent = 'Ingresar';
    }
}

function aplicarUsuarioDeSesion(usuario) {
    estado.clienteId = usuario.cliente_id;
    estado.usuario = usuario;

    // El rol de una cuenta real manda sobre el selector manual del
    // dispositivo (el botón redondo del header): si Pedro se loguea como
    // mozo, el celular pasa a comportarse como el de un mozo automáticamente,
    // sin que nadie tenga que tocar el selector. Este último queda como
    // respaldo para el caso "seguimos con un celular compartido sin cuentas
    // individuales", no como la fuente de verdad cuando sí hay login real.
    localStorage.setItem('restomind_rol', usuario.rol);
    estado.rol = usuario.rol;

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
    document.getElementById('form-login').addEventListener('submit', manejarLogin);

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
