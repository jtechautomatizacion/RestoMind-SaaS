/**
 * Vista unificada ("Todo en uno") — las tres etapas por las que pasa una
 * mesa, en una sola pantalla: tomar el pedido, cocinarlo y cobrarlo.
 *
 * Para quién es: el dueño que atiende solo. Con las pestañas separadas tiene
 * que saltar Mesas → Cocina → Mesas para cada cliente, y en cada salto pierde
 * de vista lo que estaba haciendo. Acá las tres columnas están siempre a la
 * vista y el trabajo fluye de izquierda a derecha.
 *
 * TRES DECISIONES QUE CONVIENE NO DESHACER SIN LEER ESTO:
 *
 * 1. Quién la ve sale de los ROLES que ya existen, no de una columna nueva
 *    en `clientes`. La condición es "esta cuenta ve Mesas Y ve Cocina"
 *    (`vistaUnificadaDisponible()`): admin y asistente, los dos roles de
 *    quien atiende SOLO. Mozo, cajero y cocina NO — trabajan en paralelo
 *    sobre la misma sala y cada uno necesita su pantalla enfocada; darles
 *    una vista de tres columnas los haría pisarse. Sigue saliendo de los
 *    ROLES que ya existen, no de un "modo de operación" en la base: eso
 *    sería una segunda fuente de verdad sobre quién puede hacer qué.
 *
 * 2. Es un INTERRUPTOR, no un reemplazo. La grilla de mesas de siempre queda
 *    intacta y a un toque de distancia (la preferencia se guarda por
 *    dispositivo). Si a mitad de un turno real esta vista no le acomoda, se
 *    vuelve sin perder nada.
 *
 * 3. Reusa los modales que ya existen (nuevo pedido, cuenta, cobro). Duplicar
 *    el carrito y el flujo de cobro sería duplicar la lógica de dinero —
 *    exactamente donde no se pueden tener dos versiones que se desincronicen.
 *    Esos modales YA son overlays semitransparentes (`.modal` en style.css usa
 *    rgba(10,10,10,.45)), así que el contexto de atrás se sigue viendo sin
 *    tener que construir nada nuevo.
 *
 * Lo que NO tiene, a propósito: Enter para confirmar. Cobrar mueve dinero y
 * libera la mesa; que se dispare con una tecla que se suele apretar sin mirar
 * es un cobro equivocado esperando a pasar. Los atajos de acá solo NAVEGAN.
 */

const VU_PREF_KEY = 'restomind_vista_unificada';
const VU_INTERVALO_MS = 5000;
// Ventana para juntar dígitos y poder tipear "12" en vez de saltar a la mesa 1.
const VU_TECLADO_MS = 700;

let vuActiva = false;
let vuIntervalo = null;
let vuEntregadas = [];   // comandas en 'entregado' → mesas listas para cobrar
let vuVentasHoy = null;  // solo admin (ver vuRefrescarDatos); null = no aplica
let vuTecladoBuffer = '';
let vuTecladoTimer = null;
let vuListenersPuestos = false;

/**
 * Quién opera en modo "Todo en uno".
 *
 * Antes era una regla DERIVADA ("¿ve Mesas y ve Cocina?"), y eso metía
 * adentro a cuentas que nadie había decidido meter: una `cajero,jefe_cocina`
 * existe para que UNA persona cubra dos estaciones mientras OTRAS trabajan
 * la sala, y ahí la vista de tres columnas es un riesgo real — dos personas
 * pueden cobrar la misma mesa desde dos "Todo en uno" distintos.
 *
 * Ahora es una lista explícita de roles (ROLES_VISTA_UNIFICADA en app.js,
 * espejo de la del backend): admin y asistente, las dos cuentas de quien
 * atiende SOLO. Mozo, cajero y cocina trabajan en paralelo sobre la misma
 * sala, cada uno con su pantalla enfocada en su tarea.
 */
function vistaUnificadaDisponible() {
    if (typeof ROLES_VISTA_UNIFICADA === 'undefined') return false;
    const roles = (estado && estado.roles) || [];
    return roles.some(r => ROLES_VISTA_UNIFICADA.includes(r));
}

function initVistaUnificada() {
    const sw = document.getElementById('vu-switch');
    if (!sw) return;

    if (!vistaUnificadaDisponible()) {
        sw.classList.add('hidden');
        return;
    }
    sw.classList.remove('hidden');

    // init() llega por dos caminos (sesión guardada o login recién hecho).
    // Sin esta guarda, un segundo paso dejaría dos listeners de teclado y un
    // intervalo huérfano consultando para siempre.
    if (!vuListenersPuestos) {
        vuListenersPuestos = true;
        document.querySelectorAll('#vu-tabs .vu-tab').forEach(btn => {
            btn.addEventListener('click', () => vuCambiarColumna(btn.dataset.col));
        });
        document.addEventListener('keydown', vuAtajosTeclado);
    }

    aplicarVistaUnificada(localStorage.getItem(VU_PREF_KEY) === '1');
}

/**
 * ¿Este dispositivo está en "Atiendo solo"?
 *
 * Lo consulta print.js para decidir si sacar el papel de cocina: atendiendo
 * solo, quien cocina es quien tomó el pedido y lo tiene en su pantalla, así
 * que ese papel es papel tirado (ver _papelesAlPedir en print.js).
 *
 * Se expone como función y NO se lee `localStorage` desde print.js a
 * propósito: la clave viviría escrita en dos archivos y el día que cambie,
 * uno queda viejo. Acá también está la única regla que decide el valor.
 *
 * Para un mozo, un cajero o cocina esto es SIEMPRE false —la vista unificada
 * no está disponible para esos roles (ver vistaUnificadaDisponible)— y eso es
 * correcto: si hay un mozo, hay equipo, y cocina necesita su comanda.
 */
function modoAtiendeSolo() {
    return vuActiva === true;
}

function toggleVistaUnificada(activar) {
    aplicarVistaUnificada(typeof activar === 'boolean' ? activar : !vuActiva);
}

function aplicarVistaUnificada(activa) {
    vuActiva = !!activa && vistaUnificadaDisponible();
    localStorage.setItem(VU_PREF_KEY, vuActiva ? '1' : '0');

    // Una sola clase en el <section> gobierna todo el layout: qué se ve, qué
    // se esconde y dónde queda el botón flotante. Así el CSS no tiene que
    // adivinar el estado desde tres clases repartidas por el DOM.
    const tab = document.getElementById('mozo-tab');
    if (tab) tab.classList.toggle('vu-activa', vuActiva);

    document.querySelectorAll('#vu-switch .vu-switch-btn').forEach(b => {
        b.classList.toggle('active', (b.dataset.vista === 'unificada') === vuActiva);
        b.setAttribute('aria-pressed', String((b.dataset.vista === 'unificada') === vuActiva));
    });

    // El nombre del botón entra en dos palabras; lo que HACE, no. Esta línea
    // dice en qué queda la pantalla, para que elegir no sea probar las dos.
    const hint = document.getElementById('vu-switch-hint');
    if (hint) {
        hint.textContent = vuActiva
            ? 'Mesas, cocina y cobro juntos en una pantalla. Para cuando estás sin ayuda.'
            : 'Cada uno en su pantalla: quien atiende toma pedidos, cocina cocina, caja cobra.';
        hint.classList.toggle('hidden', !vistaUnificadaDisponible());
    }

    if (vuIntervalo) {
        clearInterval(vuIntervalo);
        vuIntervalo = null;
    }
    if (vuActiva) {
        vuRefrescarDatos();
        vuIntervalo = setInterval(vuRefrescarDatos, VU_INTERVALO_MS);
    }
}

function vuCambiarColumna(col) {
    const panel = document.getElementById('vu-panel');
    if (!panel) return;
    panel.dataset.col = col;
    document.querySelectorAll('#vu-tabs .vu-tab').forEach(b => {
        b.classList.toggle('active', b.dataset.col === col);
    });
}

// ============ DATOS ============

/**
 * Las comandas en cocina NO se piden acá: las trae cocina.js, que ya las
 * consulta cada 4s para su propia pestaña y las deja en `estado.comandasCocina`
 * (avisando por `onCocinaActualizada`). Pedirlas de nuevo sería el mismo dato
 * viajando dos veces por una conexión que en un restaurante suele ser el wifi
 * del local.
 */
async function vuRefrescarDatos() {
    if (!vuActiva) return;
    try {
        estado.mesas = await api.get('/mesas');
    } catch (err) {
        // Sin señal se sigue pintando con lo último conocido: una pantalla
        // desactualizada es más útil que una en blanco a media atención.
        console.warn('Vista unificada: no se pudieron refrescar las mesas', err);
    }
    if (typeof renderMesas === 'function') renderMesas();
    await vuSincronizar();
}

/**
 * Refresca solo lo propio de esta vista y repinta. Se llama por separado de
 * vuRefrescarDatos() para los momentos en que quien llama YA trajo las mesas
 * frescas (refreshMozo, después de enviar una comanda o de cobrar): volver a
 * pedirlas ahí sería una consulta al pedo por cada acción del usuario.
 */
async function vuSincronizar() {
    if (!vuActiva) return;

    try {
        vuEntregadas = await api.get('/comandas?estado=entregado');
    } catch (err) {
        console.warn('Vista unificada: no se pudo refrescar lo cobrable', err);
    }

    // El total vendido es admin-only (/caja/estado). Una cuenta
    // `mozo,jefe_cocina` también puede usar esta vista, y para ella el pie
    // simplemente no muestra ese dato — pedirlo igual sería un 403 en cada
    // vuelta del intervalo.
    if (estado.roles.includes('admin')) {
        try {
            const caja = await api.get('/caja/estado');
            vuVentasHoy = caja ? caja.ventas_hasta_ahora : null;
        } catch (_) {
            vuVentasHoy = null;
        }
    }

    renderUnificado();
}

// Hook que dispara cocina.js cuando refresca su monitor.
function onCocinaActualizada() {
    if (vuActiva) renderUnificado();
}

// ============ ESTADO DERIVADO ============

function vuMesasEnCocina() {
    return new Set((estado.comandasCocina || []).map(c => c.numero_mesa));
}

/**
 * Tres estados visuales, no dos. Una mesa `ocupada` puede estar esperando la
 * comida o esperando que le cobren, y son dos cosas muy distintas para quien
 * atiende: en la primera no hay nada que hacer todavía, en la segunda hay
 * plata sobre la mesa.
 */
function vuEstadoMesa(mesa, enCocina) {
    if (mesa.estado !== 'ocupada') return 'libre';
    return enCocina.has(mesa.numero) ? 'cocinando' : 'por-cobrar';
}

/**
 * Mesas listas para cobrar: las que tienen comandas entregadas y NINGUNA
 * todavía en cocina.
 *
 * El filtro por cocina no es cosmético. `POST /mesas/{id}/cobrar` rechaza con
 * 400 si queda alguna comanda en 'cocina' (no se cobra comida que el cliente
 * no recibió, ver CLAUDE.md). Sin este filtro, una mesa que pidió postre
 * después aparecería acá con su botón Cobrar y el botón fallaría siempre.
 */
function vuMesasPorCobrar() {
    const enCocina = vuMesasEnCocina();
    const porMesa = new Map();

    vuEntregadas.forEach(c => {
        if (enCocina.has(c.numero_mesa)) return;
        const g = porMesa.get(c.numero_mesa) || {
            numero: c.numero_mesa, total: 0, comandas: 0, desde: c.creado_en,
        };
        g.total += c.total_cuenta;
        g.comandas += 1;
        if (c.creado_en < g.desde) g.desde = c.creado_en;
        porMesa.set(c.numero_mesa, g);
    });

    // La que espera hace más rato, primero: es la que más riesgo tiene de
    // que el cliente se canse de esperar la cuenta.
    return [...porMesa.values()].sort((a, b) => (a.desde < b.desde ? -1 : 1));
}

// ============ RENDER ============

/**
 * CON UN MODAL ABIERTO NO SE REPINTA.
 *
 * Los modales de esta app son overlays SEMITRANSPARENTES: las tres columnas
 * se siguen viendo detrás. Y acá entran dos relojes distintos — el intervalo
 * propio de esta vista (5s) y el hook que dispara cocina.js cada vez que
 * refresca su monitor (4s) — así que mientras alguien arma un pedido, el
 * fondo se reescribía cada pocos segundos.
 *
 * Eso se ve como que la pantalla "tiembla", y no es solo estético: dos de las
 * columnas se reescriben con innerHTML, así que la altura de la página cambia
 * y el fondo se reacomoda justo en el momento de más precisión — el dedo
 * eligiendo platos de una grilla. Un salto ahí es un plato equivocado.
 *
 * El guardia va ACÁ y no en los llamadores porque este es el único lugar
 * donde se pinta: cubre los dos relojes y cualquiera que se agregue después.
 * Los datos SÍ se siguen refrescando (vuRefrescarDatos y vuSincronizar corren
 * igual), así que nada queda viejo: solo se posterga el dibujo, y la vuelta
 * siguiente de cualquiera de los dos relojes lo pinta al cerrar el modal.
 *
 * Mismo criterio que los atajos de teclado, que también se apagan con un
 * modal abierto (ver vuTecla): con un modal en pantalla, la tarea es el modal.
 */
function renderUnificado() {
    if (!vuActiva) return;
    if (document.querySelector('.modal:not(.hidden)')) return;
    const enCocina = vuMesasEnCocina();
    const porCobrar = vuMesasPorCobrar();

    vuRenderMesas(enCocina);
    vuRenderCocina();
    vuRenderPorCobrar(porCobrar);
    vuRenderPie(enCocina, porCobrar);
}

/**
 * El mismo ícono 3D que usa la grilla clásica de Mesas (ver mozo.js): disco
 * con gradiente radial, sombra elíptica en el piso, brillo especular
 * arriba-izquierda y cuatro sillas. Reusarlo no es estética: es que la
 * misma mesa se vea igual en las dos pantallas, así el dueño que alterna
 * entre "Solo mesas" y "Todo en uno" no tiene que recalibrar la vista.
 *
 * A diferencia de mozo.js, acá los rellenos NO van como atributo `fill` en
 * el SVG sino desde el CSS, según la clase de estado del botón. El render
 * de esta vista reconcilia (no reescribe el nodo), así que cambiar una
 * clase es todo lo que hace falta para repintar el ícono: nada que tocar
 * en el SVG, y la transición de color la hace el navegador sola.
 */
const _VU_MESA_SVG = `
    <svg class="vu-mesa-icono" viewBox="0 0 24 24" aria-hidden="true">
        <ellipse class="vu-mesa-sombra" cx="12" cy="21.1" rx="6.6" ry="1.35"/>
        <circle class="vu-mesa-silla" cx="12" cy="2.6" r="1.65"/>
        <circle class="vu-mesa-silla" cx="12" cy="19.3" r="1.65"/>
        <circle class="vu-mesa-silla" cx="2.6" cy="11" r="1.65"/>
        <circle class="vu-mesa-silla" cx="21.4" cy="11" r="1.65"/>
        <circle class="vu-mesa-tapa" cx="12" cy="11" r="6"/>
        <ellipse class="vu-mesa-brillo" cx="9.4" cy="8.3" rx="2.5" ry="1.3"/>
    </svg>`;

/**
 * Hace cuánto espera cada mesa ocupada, en minutos.
 *
 * Se arma con lo que YA está en memoria (las comandas de cocina que
 * mantiene cocina.js + las entregadas que trae esta vista), sin pedirle
 * nada nuevo al servidor: el wifi del local suele ser el cuello de botella
 * real, y este dato no justifica una consulta más cada 5 segundos.
 */
function vuMinutosPorMesa() {
    const ahora = Date.now();
    const desde = new Map();
    const anotar = (numeroMesa, creadoEn) => {
        const t = Date.parse(creadoEn);
        if (Number.isNaN(t)) return;
        if (!desde.has(numeroMesa) || t < desde.get(numeroMesa)) desde.set(numeroMesa, t);
    };
    (estado.comandasCocina || []).forEach(c => anotar(c.numero_mesa, c.creado_en));
    vuEntregadas.forEach(c => anotar(c.numero_mesa, c.creado_en));

    const minutos = new Map();
    desde.forEach((t, numeroMesa) => {
        minutos.set(numeroMesa, Math.max(0, Math.floor((ahora - t) / 60000)));
    });
    return minutos;
}

// A partir de acá, una mesa que espera "ya es mucho". No es un umbral
// inventado: es el mismo que usa el monitor de cocina para pintar una
// comanda como atrasada (ver cocina.js), así que las dos pantallas dicen
// lo mismo sobre la misma mesa.
const VU_MINUTOS_ALERTA = 15;

/**
 * Render por RECONCILIACIÓN, no por innerHTML.
 *
 * Antes esta función reescribía la grilla entera cada 5 segundos. Eso es
 * justo lo que la hacía sentir muerta, y por tres motivos concretos:
 *
 *   1. Toda animación CSS volvía a empezar de cero en cada vuelta, así que
 *      ninguna alcanzaba a verse nunca.
 *   2. Un dedo apoyado sobre una mesa perdía el `:active` a mitad del
 *      toque, porque el nodo que estaba tocando dejaba de existir.
 *   3. La grilla tiene scroll propio (max-height: 62vh) y reemplazar su
 *      contenido lo devolvía arriba mientras alguien lo estaba usando.
 *
 * Ahora los botones se crean una vez y después solo se ACTUALIZA lo que
 * cambió. Como el nodo sobrevive entre vueltas, las transiciones de CSS
 * funcionan solas y un cambio de estado se puede destacar de verdad.
 */
function vuRenderMesas(enCocina) {
    const cont = document.getElementById('vu-mesas');
    if (!cont) return;


    // La grilla se reconstruye solo si cambió el CONJUNTO de mesas (el
    // admin agregó o quitó una), no en cada refresco de estado.
    const firma = estado.mesas.map(m => m.numero).join(',') + '|llevar';
    if (cont.dataset.firma !== firma) {
        cont.dataset.firma = firma;
        const vacio = estado.mesas.length
            ? ''
            : '<p class="vu-vacio">Aún no hay mesas configuradas.</p>';
        cont.innerHTML = vacio + estado.mesas.map((mesa, idx) => `
            <button type="button" class="vu-mesa" data-numero="${mesa.numero}"
                    onclick="vuAbrirMesa(${idx})">
                <span class="vu-mesa-barra" aria-hidden="true"></span>
                <span class="vu-mesa-cabecera">
                    <span class="vu-mesa-num">${mesa.numero}</span>
                    <span class="vu-mesa-tiempo"></span>
                </span>
                ${_VU_MESA_SVG}
                <span class="vu-mesa-detalle"></span>
            </button>
        `).join('')
        // "Para llevar" también acá, no solo en la vista clásica de Mesas.
        //
        // Quien trabaja en "Todo en uno" es justamente quien atiende SOLO —el
        // dueño o su asistente— así que es el que más lo necesita: es el mismo
        // que cobra en el mostrador. Si la opción existiera únicamente en la
        // otra vista, tendría que cambiar de pantalla para vender para llevar,
        // que es lo contrario de por qué esta vista existe.
        + `
            <button type="button" class="vu-mesa vu-mesa-llevar" data-numero="llevar"
                    onclick="abrirPedidoParaLlevar()">
                <span class="vu-mesa-barra" aria-hidden="true"></span>
                <span class="vu-mesa-cabecera">
                    <span class="vu-mesa-num vu-mesa-num-llevar">Para llevar</span>
                </span>
                <svg class="vu-mesa-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                     stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M6 8h12l-1 12H7L6 8z"/>
                    <path d="M9 8V6a3 3 0 0 1 6 0v2"/>
                </svg>
                <span class="vu-mesa-detalle">Se cobra al pedir</span>
            </button>
        `;
    }

    const minutos = vuMinutosPorMesa();
    let ocupadas = 0;

    estado.mesas.forEach((mesa, idx) => {
        const btn = cont.querySelector(`.vu-mesa[data-numero="${mesa.numero}"]`);
        if (!btn) return;

        const est = vuEstadoMesa(mesa, enCocina);
        if (est !== 'libre') ocupadas++;

        // El índice puede haberse corrido si el admin reordenó mesas, y el
        // onclick quedó fijado al construir el nodo.
        btn.setAttribute('onclick', `vuAbrirMesa(${idx})`);

        // Cambio de estado: se marca para que el CSS lo destaque un
        // instante. Es la única animación que se dispara sola acá, y
        // señala algo que de verdad pasó — no es decoración.
        const anterior = btn.dataset.estado;
        if (anterior && anterior !== est) {
            btn.classList.remove('vu-mesa--cambio');
            void btn.offsetWidth;  // reinicia la animación
            btn.classList.add('vu-mesa--cambio');
        }
        btn.dataset.estado = est;
        btn.className = `vu-mesa ${est}${btn.classList.contains('vu-mesa--cambio') ? ' vu-mesa--cambio' : ''}`;

        const espera = est === 'libre' ? null : minutos.get(mesa.numero);
        if (espera != null && espera >= VU_MINUTOS_ALERTA) btn.classList.add('urgente');

        const detalle = est === 'libre'
            ? `${mesa.capacidad}p`
            : formatCurrency(mesa.cuenta_actual);
        const elDetalle = btn.querySelector('.vu-mesa-detalle');
        if (elDetalle.textContent !== detalle) elDetalle.textContent = detalle;

        const tiempo = espera == null ? '' : (espera < 1 ? 'recién' : `${espera}'`);
        const elTiempo = btn.querySelector('.vu-mesa-tiempo');
        if (elTiempo.textContent !== tiempo) elTiempo.textContent = tiempo;

        // aria-label y NO title: el tooltip nativo del navegador aparece
        // flotando sobre las mesas vecinas y tapa justo lo que se está
        // mirando, además de no existir en una tablet (no hay hover). El
        // aria-label da la misma información al lector de pantalla sin
        // dibujar nada.
        btn.setAttribute('aria-label', est === 'libre'
            ? `Mesa ${mesa.numero} libre, ${mesa.capacidad} personas`
            : `Mesa ${mesa.numero}, ${detalle}, `
              + (est === 'cocinando' ? 'en cocina' : 'esperando la cuenta')
              + (espera != null ? `, hace ${espera} minutos` : ''));
    });

    vuBadge('mesas', ocupadas);
}

function vuRenderCocina() {
    const cont = document.getElementById('vu-cocina');
    if (!cont) return;

    const comandas = estado.comandasCocina || [];
    vuBadge('cocina', comandas.length);

    if (!comandas.length) {
        cont.innerHTML = '<p class="vu-vacio">Nada en cocina ahora mismo.</p>';
        return;
    }

    cont.innerHTML = comandas.map(c => {
        const tarde = c.minutos_transcurridos > 15;
        const platos = c.platos
            .map(p => `<li>${p.cantidad}× ${escapeHtml(p.nombre)}</li>`)
            .join('');
        return `
            <article class="vu-card ${tarde ? 'tarde' : ''}" id="vu-cocina-${c.id}">
                <header class="vu-card-top">
                    <span class="vu-card-mesa">${rotuloComanda(c)}</span>
                    <span class="vu-card-tiempo ${tarde ? 'tarde' : ''}">${c.minutos_transcurridos} min</span>
                </header>
                <ul class="vu-card-platos">${platos}</ul>
                <button type="button" class="vu-btn-listo" onclick="vuMarcarListo(${c.id})">✓ Está listo</button>
            </article>
        `;
    }).join('');
}

function vuRenderPorCobrar(porCobrar) {
    const cont = document.getElementById('vu-cobro');
    if (!cont) return;

    vuBadge('cobro', porCobrar.length);

    if (!porCobrar.length) {
        cont.innerHTML = '<p class="vu-vacio">Ninguna mesa espera la cuenta.</p>';
        return;
    }

    cont.innerHTML = porCobrar.map(g => `
        <article class="vu-card cobro">
            <header class="vu-card-top">
                <span class="vu-card-mesa">Mesa ${g.numero}</span>
                <span class="vu-card-total">${formatCurrency(g.total)}</span>
            </header>
            <p class="vu-card-nota">${g.comandas} ${g.comandas === 1 ? 'pedido entregado' : 'pedidos entregados'}</p>
            <button type="button" class="vu-btn-cobrar" onclick="vuCobrarMesa(${g.numero})">Cobrar</button>
        </article>
    `).join('');
}

function vuRenderPie(enCocina, porCobrar) {
    const pie = document.getElementById('vu-pie');
    if (!pie) return;

    const totalPorCobrar = porCobrar.reduce((s, g) => s + g.total, 0);
    const hora = new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' });

    const partes = [
        `<span class="vu-pie-item"><b>${enCocina.size}</b> en cocina</span>`,
        `<span class="vu-pie-item"><b>${formatCurrency(totalPorCobrar)}</b> por cobrar</span>`,
    ];
    if (vuVentasHoy !== null) {
        partes.push(`<span class="vu-pie-item vu-pie-fuerte"><b>${formatCurrency(vuVentasHoy)}</b> vendido</span>`);
    }
    partes.push(`<span class="vu-pie-item vu-pie-hora">${hora}</span>`);

    const cajaOk = estado.cajaAbierta !== false;
    partes.push(
        `<span class="vu-pie-caja ${cajaOk ? 'ok' : 'cerrada'}">${cajaOk ? 'Caja abierta' : 'Caja cerrada'}</span>`
    );

    pie.innerHTML = partes.join('');
}

function vuBadge(col, n) {
    const el = document.getElementById(`vu-badge-${col}`);
    if (!el) return;
    el.textContent = n;
    el.classList.toggle('cero', n === 0);
}

// ============ ACCIONES ============

// Se pasa el índice y no el número de mesa porque abrirMesa() necesita el
// objeto completo (id, estado, cuenta) y no solo su número.
function vuAbrirMesa(idx) {
    const mesa = estado.mesas[idx];
    if (mesa) abrirMesa(mesa);
}

async function vuMarcarListo(comandaId) {
    const card = document.getElementById(`vu-cocina-${comandaId}`);
    if (card) card.classList.add('saliendo');
    // marcarListo() (cocina.js) ya hace el PATCH, avisa y refresca las mesas;
    // duplicar esa llamada acá sería una segunda versión de la misma regla.
    await marcarListo(comandaId);
    // Se le vuelve a preguntar al servidor en vez de dar por hecho que salió
    // bien: marcarListo() atrapa sus propios errores, así que desde acá no hay
    // forma de distinguir éxito de fallo. Si falló, la tarjeta reaparece sola.
    // Además evita esperar hasta 4s (la vuelta del monitor de cocina) para ver
    // la mesa pasar a la columna de cobro, que es la acción más frecuente.
    if (typeof refreshCocina === 'function') await refreshCocina();
    await vuSincronizar();
}

function vuCobrarMesa(numeroMesa) {
    const mesa = estado.mesas.find(m => m.numero === numeroMesa);
    if (!mesa) {
        showToast(`No se encontró la mesa ${numeroMesa}`, 'warning');
        return;
    }
    // Abre la cuenta de siempre: muestra el detalle, el campo de DNI/RUC si
    // el restaurante emite boletas, y cobra con el mismo botón de siempre.
    abrirCuentaMesa(mesa);
}

// ============ TECLADO ============

function vuEsCampoDeTexto(el) {
    if (!el) return false;
    return el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
        || el.tagName === 'SELECT' || el.isContentEditable;
}

function vuAtajosTeclado(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    // Escribiendo en un campo (buscando un plato, tipeando un DNI) las teclas
    // son texto, no atajos.
    if (vuEsCampoDeTexto(e.target)) return;
    if (!vuActiva) return;
    // Con un modal abierto la pantalla ya está en otra tarea; saltar a otra
    // mesa desde ahí perdería el pedido a medio armar.
    if (document.querySelector('.modal:not(.hidden)')) return;

    if (!/^[0-9]$/.test(e.key)) return;

    vuTecladoBuffer += e.key;
    clearTimeout(vuTecladoTimer);
    vuTecladoTimer = setTimeout(() => {
        const numero = parseInt(vuTecladoBuffer, 10);
        vuTecladoBuffer = '';
        const mesa = estado.mesas.find(m => m.numero === numero);
        if (!mesa) {
            showToast(`No hay mesa ${numero}`, 'warning');
            return;
        }
        abrirMesa(mesa);
    }, VU_TECLADO_MS);
}
